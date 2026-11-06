import logging
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from apps.accounts.models import ShopProfile, GoogleProvisioningAuditLog
from apps.core.google_auth import get_admin_credentials

logger = logging.getLogger('apps.google_provisioner')


def sanitize_sheet_value(val):
    """
    Sanitizes values against Spreadsheet Formula Injection (CSV / Excel injection).
    If a string starts with '=', '+', '-', '@', '\t', or '\r', prefixes with a single quote (').
    """
    if val is None:
        return ''
    s = str(val)
    if s and s[0] in ('=', '+', '-', '@', '\t', '\r'):
        return f"'{s}"
    return s


def get_or_create_drive_folder(drive_service, folder_name: str) -> str:
    """
    Searches for an active, non-trashed folder with folder_name in the Admin's Google Drive.
    If found, returns its folder ID.
    If not found, creates it and returns its new folder ID.
    """
    safe_name = folder_name.replace("'", "\\'")
    query = f"name = '{safe_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"

    try:
        results = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()

        files = results.get('files', [])
        if files:
            return files[0]['id']

        # Folder does not exist, create it
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = drive_service.files().create(
            body=folder_metadata,
            fields='id'
        ).execute()
        return folder.get('id')
    except Exception as e:
        logger.error(f"Error finding/creating Google Drive folder '{folder_name}': {e}")
        raise


def create_merchant_spreadsheet(sheets_service, drive_service, folder_id: str, shop, profile):
    """
    Creates a new Google Spreadsheet with standard Koyambedu market tabs:
    - Profile
    - Suppliers
    - Flowers
    - Purchases
    - Postings
    Moves the file into folder_id, and prepopulates the Profile tab.
    Returns (spreadsheet_id, spreadsheet_url).
    """
    title = f"User - {shop.name} ({shop.code})"

    spreadsheet_body = {
        'properties': {
            'title': title
        },
        'sheets': [
            {'properties': {'title': 'Profile'}},
            {'properties': {'title': 'Suppliers'}},
            {'properties': {'title': 'Flowers'}},
            {'properties': {'title': 'Purchases'}},
            {'properties': {'title': 'Postings'}},
        ]
    }

    spreadsheet = sheets_service.spreadsheets().create(
        body=spreadsheet_body,
        fields='spreadsheetId,spreadsheetUrl'
    ).execute()

    spreadsheet_id = spreadsheet.get('spreadsheetId')
    spreadsheet_url = spreadsheet.get('spreadsheetUrl')

    # Move spreadsheet into the parent Drive folder
    try:
        file_obj = drive_service.files().get(
            fileId=spreadsheet_id,
            fields='parents'
        ).execute()
        previous_parents = ",".join(file_obj.get('parents', []))

        drive_service.files().update(
            fileId=spreadsheet_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()
    except Exception as e:
        logger.warning(f"Could not move sheet {spreadsheet_id} into folder {folder_id}: {e}")

    # Optional: share with merchant as read-only Viewer if enabled
    if getattr(settings, 'GOOGLE_SHEET_SHARE_VIEWER', False) and shop.email:
        try:
            drive_service.permissions().create(
                fileId=spreadsheet_id,
                body={
                    'type': 'user',
                    'role': 'reader',
                    'emailAddress': shop.email
                },
                fields='id'
            ).execute()
            logger.info(f"Shared sheet {spreadsheet_id} as Viewer with {shop.email}")
        except Exception as e:
            logger.warning(f"Could not share sheet with merchant {shop.email}: {e}")

    # Prepopulate headers and merchant details
    now_str = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    profile_data = [
        ['Field', 'Value'],
        ['Shop Code', sanitize_sheet_value(shop.code)],
        ['Shop / Agency Name', sanitize_sheet_value(shop.name)],
        ['Market Address', sanitize_sheet_value(shop.market_address)],
        ['Phone / WhatsApp', sanitize_sheet_value(shop.phone or profile.phone)],
        ['Owner Username', sanitize_sheet_value(profile.user.username)],
        ['Email', sanitize_sheet_value(shop.email or profile.user.email)],
        ['Account Status', 'APPROVED'],
        ['Provisioned At', now_str],
        ['Devotional Motto', sanitize_sheet_value(shop.devotional_motto)],
    ]

    suppliers_headers = [
        ['Supplier Code', 'Full Name', 'Procurement Area', 'Ledger Group', 'Commission %', 'Default Luggage (₹)', 'Opening Advance (₹)', 'Status']
    ]

    flowers_headers = [
        ['Flower Code', 'Variety Name', 'Default Rate (₹ / kg)', 'Unit', 'Status']
    ]

    purchases_headers = [
        ['Date', 'Lot ID', 'Supplier Code', 'Supplier Name', 'Flower Code', 'Flower Name', 'Weight (kg)', 'Rate (₹)', 'Gross Value (₹)', 'Boxes', 'Luggage (₹)', 'Coolie (₹)', 'Net Lot Value (₹)', 'Posting No']
    ]

    postings_headers = [
        ['Posting No', 'Supplier Code', 'Supplier Name', 'From Date', 'To Date', 'Gross Total (₹)', 'Commission (₹)', 'Luggage (₹)', 'Coolie (₹)', 'Adv Deducted (₹)', 'Total Less (₹)', 'Net Balance (₹)', 'Sealed At']
    ]

    batch_values_body = {
        'valueInputOption': 'USER_ENTERED',
        'data': [
            {'range': 'Profile!A1:B10', 'values': profile_data},
            {'range': 'Suppliers!A1:H1', 'values': suppliers_headers},
            {'range': 'Flowers!A1:E1', 'values': flowers_headers},
            {'range': 'Purchases!A1:N1', 'values': purchases_headers},
            {'range': 'Postings!A1:M1', 'values': postings_headers},
        ]
    }

    sheets_service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=batch_values_body
    ).execute()

    return spreadsheet_id, spreadsheet_url


def approve_shop_and_provision_sheet(profile_id, admin_user):
    """
    Approves a merchant registration and automatically provisions a dedicated Google Sheet.
    - Idempotent: If user already has a sheet, never creates a duplicate.
    - If Google API succeeds: sets status='APPROVED', saves sheet_id and sheet_url.
    - If Google API fails: sets status='APPROVED_SHEET_PENDING', logs error,
      and provides a retry path without losing the approval.
    Returns (success: bool, profile: ShopProfile, message: str)
    """
    if not admin_user or not getattr(admin_user, 'is_superuser', False):
        return False, None, "Permission denied. Only Super Administrators can approve shops."

    try:
        profile = ShopProfile.objects.select_related('shop', 'user').get(pk=profile_id)
    except ShopProfile.DoesNotExist:
        return False, None, f"ShopProfile with ID {profile_id} does not exist."

    # 1. Idempotency Check: Already has a sheet?
    if profile.has_sheet:
        if profile.status != ShopProfile.STATUS_APPROVED:
            profile.status = ShopProfile.STATUS_APPROVED
            profile.approved_by = admin_user
            profile.approved_at = timezone.now()
            profile.sheet_provision_error = ''
            profile.save(update_fields=['status', 'approved_by', 'approved_at', 'sheet_provision_error'])
        return True, profile, "Shop is already approved and has an active Google Sheet."

    shop = profile.shop

    # 2. Check Admin Google Credentials
    creds = get_admin_credentials()
    if not creds:
        error_msg = "Admin Google OAuth connection is not active or token has expired. Please connect Admin Google Account in Super Admin dashboard."
        with transaction.atomic():
            profile.status = ShopProfile.STATUS_APPROVED_SHEET_PENDING
            profile.approved_by = admin_user
            profile.approved_at = timezone.now()
            profile.sheet_provision_error = error_msg
            profile.save(update_fields=['status', 'approved_by', 'approved_at', 'sheet_provision_error'])

            GoogleProvisioningAuditLog.objects.create(
                admin_user=admin_user,
                shop=shop,
                action="PROVISION_FAILED_AUTH",
                status="PENDING_RETRY",
                details=error_msg
            )
        return False, profile, f"Shop marked as Approved (Sheet Pending): {error_msg}"

    # 3. Provision Google Drive Folder & Sheet
    folder_name = getattr(settings, 'GOOGLE_DRIVE_FOLDER_NAME', 'AVT Flower Market - Merchant Sheets')
    try:
        drive_service = build('drive', 'v3', credentials=creds)
        sheets_service = build('sheets', 'v4', credentials=creds)

        folder_id = get_or_create_drive_folder(drive_service, folder_name)
        sheet_id, sheet_url = create_merchant_spreadsheet(sheets_service, drive_service, folder_id, shop, profile)

        with transaction.atomic():
            profile.google_sheet_id = sheet_id
            profile.google_sheet_url = sheet_url
            profile.google_folder_id = folder_id
            profile.status = ShopProfile.STATUS_APPROVED
            profile.approved_by = admin_user
            profile.approved_at = timezone.now()
            profile.sheet_provision_error = ''
            profile.save(update_fields=[
                'google_sheet_id', 'google_sheet_url', 'google_folder_id',
                'status', 'approved_by', 'approved_at', 'sheet_provision_error'
            ])

            GoogleProvisioningAuditLog.objects.create(
                admin_user=admin_user,
                shop=shop,
                action="SHEET_PROVISIONED",
                sheet_id=sheet_id,
                folder_id=folder_id,
                status="SUCCESS",
                details=f"Successfully created dedicated sheet for '{shop.name}' ({shop.code}). URL: {sheet_url}"
            )

        logger.info(f"Successfully provisioned Google Sheet for shop {shop.code}: {sheet_url}")
        return True, profile, f"Shop approved and dedicated Google Sheet provisioned: {sheet_url}"

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to provision Google Sheet for shop {shop.code}: {error_msg}")

        with transaction.atomic():
            profile.status = ShopProfile.STATUS_APPROVED_SHEET_PENDING
            profile.approved_by = admin_user
            profile.approved_at = timezone.now()
            profile.sheet_provision_error = error_msg
            profile.save(update_fields=['status', 'approved_by', 'approved_at', 'sheet_provision_error'])

            GoogleProvisioningAuditLog.objects.create(
                admin_user=admin_user,
                shop=shop,
                action="PROVISION_FAILED",
                folder_id=locals().get('folder_id', ''),
                status="FAILURE",
                details=error_msg
            )

        return False, profile, f"Approval saved, but Google Sheet provisioning failed: {error_msg}. Status set to 'Approved (Sheet Pending)'. You can retry anytime."
