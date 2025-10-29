
from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import *

router = DefaultRouter()

# Authentication
router.register(r'auth', AuthViewSet, basename='auth')

# Core Management
router.register(r'restaurants', RestaurantViewSet, basename='restaurants')
router.register(r'branches', BranchViewSet, basename='branches')
router.register(r'menu-items', MenuItemViewSet, basename='menu-items')

# POS
router.register(r'pos', POSViewSet, basename='pos')
router.register(r'sync', SyncManagementViewSet, basename='sync')

# Finance & Analytics
router.register(r'finance', FinanceDashboardViewSet, basename='finance')
router.register(r'sales-analytics', SalesAnalyticsViewSet, basename='sales-analytics')

# AI Features
router.register(r'ai-forecast', AIForecastViewSet, basename='ai-forecast')
router.register(r'ai-comparison', AIComparisonViewSet, basename='ai-comparison')

# Inventory
router.register(r'inventory', InventoryViewSet, basename='inventory')
router.register(r'suppliers', SupplierViewSet, basename='suppliers')
router.register(r'inventory-orders', InventoryOrderViewSet, basename='inventory-orders')
router.register(r'recipes', RecipeViewSet, basename='recipes')
router.register(r'inventory-transactions', InventoryTransactionViewSet, basename='inventory-transactions')

# =============================
# AI Chat Integration (NEW)
# =============================
additional_patterns = [
    # Main AI chat endpoint - called by frontend
    path('ask-ai/', AskAIView.as_view(), name='ask-ai'),
    
    # ML model execution - called by n8n workflows
    path('run-model/', RunModelView.as_view(), name='run-model'),
    
    # Optional: Chat history
    path('chat-history/', ChatHistoryView.as_view(), name='chat-history'),
]

urlpatterns = router.urls + additional_patterns