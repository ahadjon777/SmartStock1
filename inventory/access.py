from .models import Warehouse


def display_name(user):
    """Xodimning F.I.Sh.'i (profilida yozilgan), bo'lmasa login."""
    return (user.first_name or "").strip() or user.username


def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.is_staff)


def managed_warehouses(user):
    return Warehouse.objects.filter(manager=user)


def scope(user):
    """Foydalanuvchi ko'ra oladigan omborlar: admin - hammasi, ombor mas'uli - faqat o'zinikilar."""
    return Warehouse.objects.all() if is_admin(user) else managed_warehouses(user)


def is_restricted(user):
    """Ombor mas'uli (admin emas) faqat o'z omboridagi texnika bilan ishlaydi."""
    return not is_admin(user) and managed_warehouses(user).exists()
