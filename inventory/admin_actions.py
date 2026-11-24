from django.contrib import messages
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect

from .models import Equipment
from .panel import panel_view


@panel_view(admin_only=True)
def equipment_delete(request, pk):
    """Delete one piece of equipment, including its movement history."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    equipment = get_object_or_404(Equipment, pk=pk)
    equipment.delete()
    messages.success(request, "Texnika va unga tegishli harakatlar o'chirildi")
    return redirect("panel_equipment")
