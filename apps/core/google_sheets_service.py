import logging
import time
import random
import socket
from typing import List, Dict, Any, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from apps.shops.models import Shop
from apps.accounts.models import ShopProfile, GoogleProvisioningAuditLog
from apps.core.google_auth import get_admin_credentials
from apps.core.google_sheets_provisioner import sanitize_sheet_value

logger = logging.getLogger('apps.google_service')


class SheetNotProvisionedError(Exception):
    """Raised when an operation is attempted on a shop that has no provisioned Google Sheet."""
    pass


class GoogleSheetsAPIError(Exception):
    """Raised when a Google Sheets API call fails after exhausting retries."""
    pass


def execute_with_retry(call_func, max_retries: int = 3, initial_delay: float = 0.5, backoff_factor: float = 2.0):
    """
    Executes a callable with exponential backoff and jitter for transient failures:
    - HTTP 429 (Rate Limit / Quota Exceeded)
    - HTTP 500, 502, 503, 504 (Server Errors)
    - Socket and SSL network errors
    """
    retries = 0
    delay = initial_delay

    while True:
        try:
            return call_func()
        except HttpError as err:
            status_code = getattr(err.resp, 'status', None)
            is_retriable = status_code in (429, 500, 502, 503, 504)

            if is_retriable and retries < max_retries:
                retries += 1
                # Add jitter (10-30% randomized)
                jitter = delay * random.uniform(0.1, 0.3)
                sleep_time = delay + jitter
                logger.warning(
                    f"Google Sheets API HTTP {status_code}. Retrying ({retries}/{max_retries}) in {sleep_time:.2f}s..."
                )
                time.sleep(sleep_time)
                delay *= backoff_factor
            else:
                logger.error(f"Google Sheets API error {status_code} after {retries} retries: {err}")
                raise GoogleSheetsAPIError(f"Google Sheets API error ({status_code}): {err}") from err
        except (socket.error, ConnectionError, TimeoutError) as net_err:
            if retries < max_retries:
                retries += 1
                sleep_time = delay + (delay * random.uniform(0.1, 0.3))
                logger.warning(
                    f"Network error: {net_err}. Retrying ({retries}/{max_retries}) in {sleep_time:.2f}s..."
                )
                time.sleep(sleep_time)
                delay *= backoff_factor
            else:
                logger.error(f"Network error after {retries} retries: {net_err}")
                raise GoogleSheetsAPIError(f"Network communication failed with Google Sheets: {net_err}") from net_err
        except Exception as e:
            logger.error(f"Unexpected error executing Google Sheets operation: {e}")
            raise


class UserSheetService:
    """
    Per-merchant Google Sheets Data Access Layer.
    Strictly isolated: operations are locked exclusively to the authenticated merchant's
    assigned Google Sheet ID. Formula-injection sanitization is applied on all writes.
    """

    def __init__(self, target):
        if isinstance(target, ShopProfile):
            self.profile = target
            self.shop = target.shop
        elif isinstance(target, Shop):
            self.shop = target
            profile = target.profiles.first()
            if not profile:
                raise SheetNotProvisionedError(f"Shop '{self.shop.code}' has no associated ShopProfile.")
            self.profile = profile
        elif hasattr(target, 'shopprofile'):
            self.profile = target.shopprofile
            self.shop = self.profile.shop
        else:
            raise SheetNotProvisionedError(f"Cannot resolve ShopProfile from target {target}")

        if not self.profile.google_sheet_id:
            raise SheetNotProvisionedError(
                f"Shop '{self.shop.code}' has no Google Sheet provisioned. Status: {self.profile.status}."
            )

        self.sheet_id: str = self.profile.google_sheet_id
        self._sheets_service = None

    @classmethod
    def for_user(cls, user):
        """Factory method to instantiate UserSheetService safely from a request.user."""
        if not user.is_authenticated:
            raise PermissionError("Unauthenticated user cannot access sheet service.")
        try:
            profile = user.shopprofile
            return cls(profile)
        except Exception as e:
            raise SheetNotProvisionedError(f"User {user.username} has no associated merchant shop profile.") from e

    @property
    def sheets_service(self):
        if self._sheets_service is None:
            creds = get_admin_credentials()
            if not creds:
                raise PermissionError("Google Admin credentials are not connected or authorization is required.")
            self._sheets_service = build('sheets', 'v4', credentials=creds, cache_discovery=False)
        return self._sheets_service

    @classmethod
    def sanitize_rows(cls, rows: List[List[Any]]) -> List[List[Any]]:
        """
        Deep-sanitizes a 2D matrix of values against formula injection before sending to Google Sheets.
        """
        sanitized = []
        for row in rows:
            sanitized_row = [sanitize_sheet_value(cell) for cell in row]
            sanitized.append(sanitized_row)
        return sanitized

    def read_rows(self, tab: str, range_name: Optional[str] = None) -> List[List[Any]]:
        """
        Reads raw cell rows from a specific tab and optional A1-notation range.
        e.g. read_rows('Suppliers', 'A2:F50') or read_rows('Flowers')
        """
        full_range = f"'{tab}'!{range_name}" if range_name else f"'{tab}'"

        def _fetch():
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=full_range
            ).execute()
            return result.get('values', [])

        return execute_with_retry(_fetch)

    def append_rows(self, tab: str, rows: List[List[Any]], value_input_option: str = 'USER_ENTERED') -> Dict[str, Any]:
        """
        Appends sanitized rows of data to the specified tab.
        """
        if not rows:
            return {'updates': {'updatedRows': 0}}

        sanitized_rows = self.sanitize_rows(rows)
        target_range = f"'{tab}'!A1"

        def _append():
            return self.sheets_service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range=target_range,
                valueInputOption=value_input_option,
                insertDataOption='INSERT_ROWS',
                body={'values': sanitized_rows}
            ).execute()

        return execute_with_retry(_append)

    def batch_update_rows(self, tab: str, updates: List[Dict[str, Any]], value_input_option: str = 'USER_ENTERED') -> Dict[str, Any]:
        """
        Batch updates multiple cell ranges on the specified tab.
        Each item in updates must be:
        {
            'range': 'A2:B2' or "'Tab'!A2:B2",
            'values': [[val1, val2]]
        }
        """
        if not updates:
            return {'totalUpdatedCells': 0}

        prepared_data = []
        for item in updates:
            raw_range = item.get('range', '')
            if '!' not in raw_range:
                cell_range = f"'{tab}'!{raw_range}"
            else:
                cell_range = raw_range

            prepared_data.append({
                'range': cell_range,
                'values': self.sanitize_rows(item.get('values', []))
            })

        body = {
            'valueInputOption': value_input_option,
            'data': prepared_data
        }

        def _batch():
            return self.sheets_service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.sheet_id,
                body=body
            ).execute()

        return execute_with_retry(_batch)

    def clear_range(self, tab: str, range_name: str) -> Dict[str, Any]:
        """
        Clears cells within the specified range (e.g. range_name='A2:Z100').
        """
        full_range = f"'{tab}'!{range_name}"

        def _clear():
            return self.sheets_service.spreadsheets().values().clear(
                spreadsheetId=self.sheet_id,
                range=full_range,
                body={}
            ).execute()

        return execute_with_retry(_clear)

    def get_tab_records(self, tab: str) -> List[Dict[str, Any]]:
        """
        Convenience method: Reads tab rows, treats row 1 as column keys,
        and returns a list of dictionaries.
        """
        rows = self.read_rows(tab)
        if not rows or len(rows) < 2:
            return []

        headers = [str(h).strip() for h in rows[0]]
        records = []
        for row in rows[1:]:
            record = {}
            for idx, header in enumerate(headers):
                record[header] = row[idx] if idx < len(row) else ''
            records.append(record)
        return records

    def log_audit(self, action: str, status: str, admin_user=None, error_message: str = ''):
        """
        Helper to record audit entries in GoogleProvisioningAuditLog.
        """
        GoogleProvisioningAuditLog.objects.create(
            shop=self.shop,
            admin_user=admin_user,
            action=action,
            status=status,
            google_sheet_id=self.sheet_id,
            error_message=error_message
        )
