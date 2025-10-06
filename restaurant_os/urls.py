from rest_framework.routers import DefaultRouter
from .views import (
    MenuItemViewSet, SaleViewSet, DailySaleViewSet,
    InventoryViewSet, SupplierViewSet, InventoryOrderViewSet
)

router = DefaultRouter()
router.register(r'menu-items', MenuItemViewSet)
router.register(r'sales', SaleViewSet)
router.register(r'daily-sales', DailySaleViewSet)
router.register(r'inventory', InventoryViewSet)
router.register(r'suppliers', SupplierViewSet)
router.register(r'inventory-orders', InventoryOrderViewSet)

urlpatterns = router.urls
