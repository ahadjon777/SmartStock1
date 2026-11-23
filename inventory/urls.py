from django.urls import path

from . import panel, views

urlpatterns = [
    path("", views.scan, name="scan"),
    path("api/scan/", views.scan_api, name="scan_api"),
    path("labels/", views.labels, name="labels"),
    path("assign/", views.assign, name="assign"),
    path("api/assign/", views.assign_api, name="assign_api"),
    path("stats/", views.dashboard, name="dashboard"),
    path("panel/", panel.home, name="panel_home"),
    path("panel/out/", panel.out_now, name="panel_out"),
    path("panel/equipment/", panel.equipment_list, name="panel_equipment"),
    path("panel/equipment/new/", panel.equipment_edit, name="panel_equipment_new"),
    path("panel/equipment/<int:pk>/", panel.equipment_edit, name="panel_equipment_edit"),
    path("panel/import/", panel.import_excel, name="panel_import"),
    path("panel/warehouses/", panel.warehouse_list, name="panel_warehouses"),
    path("panel/warehouses/new/", panel.warehouse_edit, name="panel_warehouse_new"),
    path("panel/warehouses/<int:pk>/", panel.warehouse_edit, name="panel_warehouse_edit"),
    path("panel/staff/", panel.staff_list, name="panel_staff"),
    path("panel/staff/new/", panel.staff_edit, name="panel_staff_new"),
    path("panel/staff/<int:pk>/", panel.staff_edit, name="panel_staff_edit"),
]
