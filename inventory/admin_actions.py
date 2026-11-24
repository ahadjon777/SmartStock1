@panel_view(admin_only=True)
def equipment_delete(request, pk):
    if request.method == "POST":
        equipment = get_object_or_404(Equipment, pk=pk)
        equipment.delete()
        messages.success(request, "Texnika va unga tegishli harakatlar o'chirildi")
    return redirect("panel_equipment")
