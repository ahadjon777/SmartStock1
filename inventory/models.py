from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models


class Region(models.TextChoices):
    TASHKENT_CITY = "tashkent_city", "Toshkent shahri"
    TASHKENT_REGION = "tashkent_region", "Toshkent viloyati"
    OTHER_REGIONS = "other_regions", "Boshqa viloyatlar"
    ABROAD = "abroad", "Qo'shni davlatlar"


class Warehouse(models.Model):
    name = models.CharField("Ombor", max_length=100, unique=True)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name="Mas'ul xodim",
    )

    class Meta:
        verbose_name = "Ombor"
        verbose_name_plural = "Omborlar"

    def __str__(self):
        return self.name


class Equipment(models.Model):
    class Status(models.TextChoices):
        IN_STOCK = "in_stock", "Omborda"
        OUT = "out", "Tadbirda"

    code = models.CharField("QR kod", max_length=64, unique=True)
    name = models.CharField("Nomi", max_length=200)
    manufactured_year = models.PositiveSmallIntegerField("Ishlab chiqarilgan yili", null=True, blank=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, verbose_name="Ombor")
    status = models.CharField("Holati", max_length=10, choices=Status.choices, default=Status.IN_STOCK)

    class Meta:
        verbose_name = "Texnika"
        verbose_name_plural = "Texnikalar"

    def __str__(self):
        return f"{self.code} - {self.name}"


class Movement(models.Model):
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="movements", verbose_name="Texnika")
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, verbose_name="Bergan xodim",
    )
    taken_by = models.CharField("Olgan shaxs (F.I.Sh.)", max_length=150)
    region = models.CharField("Hudud", max_length=20, choices=Region.choices)
    holder = models.CharField("Biriktirilgan shaxs (F.I.Sh.)", max_length=150, blank=True)
    holder_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="held", verbose_name="Biriktirilgan xodim (login)",
    )
    event = models.CharField("Tadbir", max_length=200, blank=True)
    out_at = models.DateTimeField("Chiqqan vaqt")
    in_at = models.DateTimeField("Qaytgan vaqt", null=True, blank=True)
    manual_hours = models.DecimalField(
        "Qo'lda ishlash vaqti (soat)", max_digits=7, decimal_places=2, null=True, blank=True,
    )

    class Meta:
        verbose_name = "Harakat"
        verbose_name_plural = "Harakatlar"
        ordering = ["-out_at"]

    @property
    def total_hours(self):
        if not self.in_at:
            return None
        return Decimal((self.in_at - self.out_at) / timedelta(hours=1)).quantize(Decimal("0.01"))

    @property
    def work_hours(self):
        """Real ishlash vaqti: chiqish-qaytish vaqtining yarmi, yoki qo'lda kiritilgani."""
        if self.manual_hours is not None:
            return self.manual_hours
        total = self.total_hours
        return None if total is None else (total / 2).quantize(Decimal("0.01"))

    def __str__(self):
        return f"{self.equipment} -> {self.taken_by}"


class SecurityEvent(models.Model):
    kind = models.CharField("Turi", max_length=30, db_index=True)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    username = models.CharField("Login", max_length=150, blank=True)
    detail = models.CharField("Tafsilot", max_length=300, blank=True)
    created_at = models.DateTimeField("Vaqt", auto_now_add=True, db_index=True)
    handled = models.BooleanField("Ko'rib chiqildi", default=False)

    class Meta:
        verbose_name = "Xavfsizlik hodisasi"
        verbose_name_plural = "Xavfsizlik hodisalari"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.kind} {self.ip or ''} {self.username}"


class BlockedIP(models.Model):
    ip = models.GenericIPAddressField("IP", unique=True)
    reason = models.CharField("Sabab", max_length=200, blank=True)
    created_at = models.DateTimeField("Bloklangan vaqt", auto_now_add=True)

    class Meta:
        verbose_name = "Bloklangan IP"
        verbose_name_plural = "Bloklangan IP'lar"

    def __str__(self):
        return self.ip


class SecurityState(models.Model):
    """Bitta qatorli sozlama: lockdown (favqulodda yopish) rejimi."""
    lockdown = models.BooleanField("Lockdown", default=False)
    updated_at = models.DateTimeField(auto_now=True)
