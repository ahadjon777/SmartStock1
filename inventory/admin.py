from django.contrib import admin

from .models import Equipment, Movement, Warehouse


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "manager")


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "warehouse", "status")
    list_filter = ("warehouse", "status")
    search_fields = ("code", "name")


@admin.register(Movement)
class MovementAdmin(admin.ModelAdmin):
    list_display = ("equipment", "issued_by", "returned_by", "taken_by", "region", "out_at", "in_at", "work_hours")
    list_filter = ("region", "issued_by", "returned_by")
    search_fields = ("equipment__code", "equipment__name", "taken_by", "event")


from .models import BlockedIP, SecurityEvent  # noqa: E402


@admin.register(SecurityEvent)
class SecurityEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "ip", "username", "detail", "handled")
    list_filter = ("kind", "handled")
    search_fields = ("ip", "username")


@admin.register(BlockedIP)
class BlockedIPAdmin(admin.ModelAdmin):
    list_display = ("ip", "reason", "created_at")
