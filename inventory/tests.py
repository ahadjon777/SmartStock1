from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from . import security
from .models import Equipment, SecurityEvent, Warehouse

User = get_user_model()


class EquipmentDeleteTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="test-pass", is_staff=True)
        self.warehouse = Warehouse.objects.create(name="Main")
        self.equipment = Equipment.objects.create(code="EQ-1", name="Camera", warehouse=self.warehouse)

    def test_admin_can_delete_equipment_with_post(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("panel_equipment_delete", args=[self.equipment.pk]))
        self.assertRedirects(response, reverse("panel_equipment"))
        self.assertFalse(Equipment.objects.filter(pk=self.equipment.pk).exists())

    def test_get_is_not_allowed(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("panel_equipment_delete", args=[self.equipment.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Equipment.objects.filter(pk=self.equipment.pk).exists())

    def test_non_admin_cannot_delete_equipment(self):
        user = User.objects.create_user(username="staff", password="test-pass")
        self.client.force_login(user)
        response = self.client.post(reverse("panel_equipment_delete", args=[self.equipment.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Equipment.objects.filter(pk=self.equipment.pk).exists())


class SecurityAlertTests(TestCase):
    @override_settings(SECURITY_FAIL_LIMIT=2, SECURITY_USER_FAIL_LIMIT=99)
    @patch("inventory.security.notify")
    def test_bruteforce_threshold_sends_alert(self, notify):
        security.on_login_failed("192.0.2.10", "someone")
        security.on_login_failed("192.0.2.10", "someone")
        self.assertTrue(SecurityEvent.objects.filter(kind="bruteforce", ip="192.0.2.10").exists())
        notify.assert_called_once()
