from core.models import Category
Category.objects.get_or_create(name="Web", description="Web security challenges")
print("Test seed complete: Category 'Web' created!")