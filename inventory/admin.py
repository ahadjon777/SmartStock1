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
    list_display = ("equipment", "taken_by", "region", "out_at", "in_at", "work_hours")
    list_filter = ("region",)
    search_fields = ("equipment__code", "taken_by", "event")
