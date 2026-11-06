from django.test import TestCase, Client
from django.contrib.auth.models import User
from apps.shops.models import Shop
from apps.accounts.models import ShopProfile

class NavigationAuthRenderingTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        # Approved Shop & User
        self.shop = Shop.objects.create(code='shop-avt-nav', name='AVT Agency')
        self.user_shop = User.objects.create_user(username='shop_clerk', password='Password123!')
        self.profile = ShopProfile.objects.create(
            user=self.user_shop, shop=self.shop, status=ShopProfile.STATUS_APPROVED
        )

        # Superuser
        self.superuser = User.objects.create_superuser(username='super_user', password='SuperPassword123!')

    def test_anonymous_nav_rendering(self):
        """Logged-out visitor sees only Logo, Theme Toggle, Register Shop, and Sign In."""
        resp = self.client.get('/login/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        # Visible elements
        self.assertIn('AVT FLOWER TERMINAL', content)
        self.assertIn('theme-icon-btn', content)
        self.assertIn('Register Shop', content)
        self.assertIn('Sign In', content)

        # Hidden elements for anonymous visitor
        self.assertNotIn('>Terminal<', content)
        self.assertNotIn('>Suppliers<', content)
        self.assertNotIn('>Flowers<', content)
        self.assertNotIn('>Bills<', content)
        self.assertNotIn('>Admin<', content)
        self.assertNotIn('Logout', content)

    def test_approved_shop_user_nav_rendering(self):
        """Logged-in approved merchant sees trading nav tabs and shop pill, but not Super Admin."""
        self.client.force_login(self.user_shop)
        resp = self.client.get('/terminal/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        # Allowed links
        self.assertIn('Terminal', content)
        self.assertIn('Suppliers', content)
        self.assertIn('Flowers', content)
        self.assertIn('Bills', content)
        self.assertIn('AVT Agency', content)
        self.assertIn('Logout', content)

        # Super Admin must NOT be rendered for regular shop user
        self.assertNotIn('>Admin<', content)
        self.assertNotIn('/super-admin/', content)

    def test_superuser_nav_rendering(self):
        """Superuser sees the Admin link in addition to the standard tabs."""
        self.client.force_login(self.superuser)
        resp = self.client.get('/super-admin/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        self.assertIn('Admin', content)
        self.assertIn('/super-admin/', content)
        self.assertIn('Logout', content)
