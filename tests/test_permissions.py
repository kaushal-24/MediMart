from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import UserCapabilityOverride, UserProfile
from accounts.permissions import has_capability


User = get_user_model()


class CapabilityPermissionTests(TestCase):
    def make_user(self, username, role, **kwargs):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@gmail.com",
            password="Testpass123!",
            **kwargs,
        )
        UserProfile.objects.create(user=user, role=role)
        return user

    def test_catalog_manager_is_scoped_to_catalog_capabilities(self):
        user = self.make_user("catalog_manager", UserProfile.Role.CATALOG_MANAGER)

        self.assertTrue(has_capability(user, "catalog.manage"))
        self.assertFalse(has_capability(user, "finance.manage"))

    def test_support_staff_cannot_access_catalog_management(self):
        user = self.make_user("support_staff", UserProfile.Role.SUPPORT_STAFF)

        self.assertTrue(has_capability(user, "support.manage"))
        self.assertFalse(has_capability(user, "catalog.manage"))

    def test_inactive_accounts_cannot_use_capabilities(self):
        user = self.make_user("inactive_admin", UserProfile.Role.ADMIN)
        user.is_active = False
        user.save(update_fields=["is_active"])

        self.assertFalse(has_capability(user, "dashboard.operations"))

    def test_superuser_can_use_all_defined_capabilities(self):
        user = self.make_user("root_user", UserProfile.Role.CUSTOMER, is_superuser=True)

        self.assertTrue(has_capability(user, "catalog.manage"))
        self.assertTrue(has_capability(user, "audit.view"))

    def test_capability_override_can_grant_or_deny_an_individual_action(self):
        user = self.make_user("support_catalog_exception", UserProfile.Role.SUPPORT_STAFF)

        UserCapabilityOverride.objects.create(
            user=user,
            capability="catalog.manage",
            is_granted=True,
            reason="Temporary catalogue correction assignment",
        )
        self.assertTrue(has_capability(user, "catalog.manage"))

        override = UserCapabilityOverride.objects.get(user=user, capability="catalog.manage")
        override.is_granted = False
        override.save(update_fields=["is_granted", "updated_at"])
        self.assertFalse(has_capability(user, "catalog.manage"))
