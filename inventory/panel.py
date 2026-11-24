from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .access import is_admin, managed_warehouses, scope
from .forms import EquipmentForm, StaffForm, WarehouseForm
from .importer import import_workbook
from .models import Equipment, Movement, Warehouse

User = get_user_model()

SORT_DIRECTIONS = {"asc", "desc"}


def panel_view(admin_only=False):
    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if admin_only and not is_admin(user):
                raise PermissionDenied
            if not is_admin(user) and not managed_warehouses(user).exists():
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapper
    return deco


def render_panel(request, template, tab, ctx=None):
    ctx = dict(ctx or {})
    ctx.update(tab=tab, panel_admin=is_admin(request.user))
    return render(request, template, ctx)


def human(delta):
    mins = int(delta.total_seconds() // 60)
    days, rest = divmod(mins, 1440)
    hours, minutes = divmod(rest, 60)
    if days:
        return f"{days} kun {hours} soat"
    if hours:
        return f"{hours} soat {minutes} daq"
    return f"{minutes} daq"


def sort_context(request, allowed):
    current = request.GET.get("sort", "")
    direction = request.GET.get("direction", "asc")
    if direction not in SORT_DIRECTIONS:
        direction = "asc"
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("sort", None)
    params.pop("direction", None)
    links = {}
    for key in allowed:
        next_direction = "desc" if current == key and direction == "asc" else "asc"
        query = params.copy()
        query["sort"] = key
        query["direction"] = next_direction
        links[key] = "?" + query.urlencode()
    return {"sort_links": links, "sort_by": current, "sort_direction": direction}


def apply_sort(queryset, request, allowed, default):
    key = request.GET.get("sort", "")
    direction = request.GET.get("direction", "asc")
    if key not in allowed:
        key = default
    if direction not in SORT_DIRECTIONS:
        direction = "asc"
    field = allowed[key]
    return queryset.order_by(("-" if direction == "desc" else "") + field)


@panel_view()
def home(request):
    wh = scope(request.user)
    eq = Equipment.objects.filter(warehouse__in=wh)
    mv = Movement.objects.filter(equipment__warehouse__in=wh)
    today = timezone.localdate()
    return render_panel(request, "panel/home.html", "home", {
        "total": eq.count(), "out": eq.filter(status=Equipment.Status.OUT).count(),
        "today_out": mv.filter(out_at__date=today).count(), "today_in": mv.filter(in_at__date=today).count(),
        "warehouses": wh.annotate(total=Count("equipment"), out=Count("equipment", filter=Q(equipment__status=Equipment.Status.OUT))),
        "recent": mv.select_related("equipment")[:10],
    })


@panel_view()
def out_now(request):
    allowed = {"date": "out_at", "person": "taken_by", "code": "equipment__code", "name": "equipment__name", "warehouse": "equipment__warehouse__name"}
    qs = Movement.objects.filter(in_at__isnull=True, equipment__warehouse__in=scope(request.user)).select_related("equipment", "equipment__warehouse").order_by("taken_by", "out_at")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(equipment__code__icontains=q) | Q(equipment__name__icontains=q) | Q(taken_by__icontains=q) | Q(holder__icontains=q))
    qs = apply_sort(qs, request, allowed, "date")
    now = timezone.now()
    rows = list(qs)
    for movement in rows:
        movement.since = human(now - movement.out_at)
    return render_panel(request, "panel/out.html", "out", {"rows": rows, "q": q, **sort_context(request, allowed)})


@panel_view()
def equipment_list(request):
    wh = scope(request.user)
    allowed = {"code": "code", "name": "name", "warehouse": "warehouse__name", "status": "status"}
    qs = Equipment.objects.filter(warehouse__in=wh).select_related("warehouse")
    if request.GET.get("warehouse", "").isdigit():
        qs = qs.filter(warehouse_id=request.GET["warehouse"])
    if request.GET.get("status") in Equipment.Status.values:
        qs = qs.filter(status=request.GET["status"])
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    qs = apply_sort(qs, request, allowed, "code")
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render_panel(request, "panel/equipment.html", "equipment", {"page": page, "warehouses": wh, "statuses": Equipment.Status.choices, **sort_context(request, allowed)})


@panel_view()
def equipment_edit(request, pk=None):
    wh = scope(request.user)
    obj = get_object_or_404(Equipment, pk=pk, warehouse__in=wh) if pk else None
    form = EquipmentForm(request.POST or None, instance=obj, warehouses=wh)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Saqlandi")
        return redirect("panel_equipment")
    return render_panel(request, "panel/form.html", "equipment", {"form": form, "title": "Texnikani tahrirlash" if obj else "Yangi texnika", "back": "panel_equipment"})


@panel_view(admin_only=True)
def equipment_bulk(request):
    if request.method != "POST":
        return redirect("panel_equipment")
    ids = request.POST.getlist("equipment_ids")
    items = Equipment.objects.filter(pk__in=ids)
    action = request.POST.get("action")
    if not ids:
        messages.warning(request, "Avval texnikalarni belgilang")
    elif action == "delete":
        count = items.count()
        items.delete()
        messages.success(request, f"{count} ta texnika va ularga tegishli harakatlar o'chirildi")
    elif action == "move":
        warehouse = get_object_or_404(Warehouse, pk=request.POST.get("warehouse"))
        movable = items.filter(status=Equipment.Status.IN_STOCK)
        count = movable.update(warehouse=warehouse)
        skipped = items.exclude(status=Equipment.Status.IN_STOCK).count()
        msg = f"{count} ta texnika {warehouse.name} omboriga biriktirildi"
        if skipped:
            msg += f"; tadbirda bo'lgan {skipped} ta texnika o'tkazilmadi"
        messages.success(request, msg)
    else:
        messages.error(request, "Amalni tanlang")
    return redirect("panel_equipment")


@panel_view(admin_only=True)
def import_excel(request):
    if request.method == "POST" and request.FILES.get("file"):
        warehouse = get_object_or_404(Warehouse, pk=request.POST.get("warehouse"))
        try:
            result = import_workbook(request.FILES["file"], warehouse)
            messages.success(request, f"Yangi: {result[0]}, yangilandi: {result[1]}, o'tkazildi: {result[2]}")
        except Exception as exc:
            messages.error(request, f"Faylni o'qib bo'lmadi: {exc}")
        return redirect("panel_import")
    return render_panel(request, "panel/import.html", "equipment", {"warehouses": Warehouse.objects.order_by("name")})


@panel_view(admin_only=True)
def warehouse_list(request):
    allowed = {"name": "name", "manager": "manager__username", "total": "total", "out": "out"}
    rows = Warehouse.objects.select_related("manager").annotate(total=Count("equipment"), out=Count("equipment", filter=Q(equipment__status=Equipment.Status.OUT)))
    rows = apply_sort(rows, request, allowed, "name")
    return render_panel(request, "panel/warehouses.html", "warehouses", {"rows": rows, **sort_context(request, allowed)})


@panel_view(admin_only=True)
def warehouse_edit(request, pk=None):
    obj = get_object_or_404(Warehouse, pk=pk) if pk else None
    form = WarehouseForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Saqlandi")
        return redirect("panel_warehouses")
    return render_panel(request, "panel/form.html", "warehouses", {"form": form, "title": "Omborni tahrirlash" if obj else "Yangi ombor", "back": "panel_warehouses"})


@panel_view(admin_only=True)
def warehouse_delete(request, pk):
    if request.method == "POST":
        warehouse = get_object_or_404(Warehouse, pk=pk)
        try:
            warehouse.delete()
            messages.success(request, "Ombor o'chirildi")
        except ProtectedError:
            messages.error(request, "Omborda texnikalar bor. Avval ularni boshqa omborga o'tkazing.")
    return redirect("panel_warehouses")


@panel_view(admin_only=True)
def staff_list(request):
    allowed = {"username": "username", "name": "first_name", "role": "is_staff", "active": "is_active"}
    users = apply_sort(User.objects.prefetch_related("warehouse_set"), request, allowed, "username")
    return render_panel(request, "panel/staff.html", "staff", {"users": users, **sort_context(request, allowed)})


@panel_view(admin_only=True)
def staff_edit(request, pk=None):
    obj = get_object_or_404(User, pk=pk) if pk else None
    initial = {}
    if obj:
        initial = {"username": obj.username, "full_name": obj.first_name, "is_admin": obj.is_staff or obj.is_superuser, "is_active": obj.is_active, "warehouses": Warehouse.objects.filter(manager=obj)}
    form = StaffForm(request.POST or None, initial=initial, user=obj)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        user = obj or User()
        user.username = data["username"]
        user.first_name = data["full_name"]
        if user != request.user:
            user.is_staff = data["is_admin"]
            user.is_active = data["is_active"]
        if data["password"]:
            user.set_password(data["password"])
        user.save()
        chosen = data["warehouses"]
        Warehouse.objects.filter(manager=user).exclude(pk__in=chosen).update(manager=None)
        Warehouse.objects.filter(pk__in=chosen).update(manager=user)
        messages.success(request, "Saqlandi")
        return redirect("panel_staff")
    return render_panel(request, "panel/form.html", "staff", {"form": form, "title": "Xodimni tahrirlash" if obj else "Yangi xodim", "back": "panel_staff"})


@panel_view(admin_only=True)
def staff_delete(request, pk):
    if request.method == "POST":
        user = get_object_or_404(User, pk=pk)
        if user.pk == request.user.pk:
            messages.error(request, "O'zingizning akkauntingizni o'chira olmaysiz")
        elif user.is_superuser:
            messages.error(request, "Superadmin akkauntini bu paneldan o'chirib bo'lmaydi")
        else:
            user.delete()
            messages.success(request, "Xodim o'chirildi")
    return redirect("panel_staff")
