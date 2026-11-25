from django.urls import path

from . import admin_actions, panel, views

urlpatterns = [
    path("", views.scan, name="scan"),
    path("out/", views.checkout, name="checkout"),
    path("api/checkout/", views.checkout_api, name="checkout_api"),
    path("take/", views.take, name="take"),
    path("api/take/", views.take_api, name="take_api"),
    path("api/release/", views.release_api, name="release_api"),
    path("in/", views.checkin, name="checkin"),
    path("api/checkin/", views.checkin_api, name="checkin_api"),
    path("progress/", views.progress, name="progress"),
    path("labels/", views.labels, name="labels"),
    path("stats/", views.dashboard, name="dashboard"),
    path("panel/", panel.home, name="panel_home"),
    path("panel/out/", panel.out_now, name="panel_out"),
    path("panel/equipment/", panel.equipment_list, name="panel_equipment"),
    path("panel/equipment/bulk/", panel.equipment_bulk, name="panel_equipment_bulk"),
    path("panel/equipment/new/", panel.equipment_edit, name="panel_equipment_new"),
    path("panel/equipment/<int:pk>/delete/", admin_actions.equipment_delete, name="panel_equipment_delete"),
    path("panel/equipment/<int:pk>/", panel.equipment_edit, name="panel_equipment_edit"),
    path("panel/import/", panel.import_excel, name="panel_import"),
    path("panel/warehouses/", panel.warehouse_list, name="panel_warehouses"),
    path("panel/warehouses/new/", panel.warehouse_edit, name="panel_warehouse_new"),
    path("panel/warehouses/<int:pk>/delete/", panel.warehouse_delete, name="panel_warehouse_delete"),
    path("panel/warehouses/<int:pk>/", panel.warehouse_edit, name="panel_warehouse_edit"),
    path("panel/staff/", panel.staff_list, name="panel_staff"),
    path("panel/staff/new/", panel.staff_edit, name="panel_staff_new"),
    path("panel/staff/<int:pk>/delete/", panel.staff_delete, name="panel_staff_delete"),
    path("panel/staff/<int:pk>/", panel.staff_edit, name="panel_staff_edit"),
]
