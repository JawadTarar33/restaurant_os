from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import *

# =============================
# ROUTER REGISTRATION
# =============================
router = DefaultRouter()

# Authentication
router.register(r'auth', AuthViewSet, basename='auth')

# Core Management
router.register(r'restaurants', RestaurantViewSet, basename='restaurants')
router.register(r'branches', BranchViewSet, basename='branches')
router.register(r'categories', CategoryViewSet, basename='categories')
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

# Inventory Management
router.register(r'inventory', InventoryViewSet, basename='inventory')
router.register(r'suppliers', SupplierViewSet, basename='suppliers')
router.register(r'inventory-orders', InventoryOrderViewSet, basename='inventory-orders')
router.register(r'recipes', RecipeViewSet, basename='recipes')
router.register(r'inventory-transactions', InventoryTransactionViewSet, basename='inventory-transactions')
router.register(r'ingredients', IngredientViewSet, basename='ingredients')

# =============================
# ADDITIONAL NON-ROUTER ENDPOINTS
# =============================
additional_patterns = [
    # AI Chat Integration
    path('ask-ai/', AskAIView.as_view(), name='ask-ai'),
    path('run-model/', RunModelView.as_view(), name='run-model'),
    path('chat-history/', ChatHistoryView.as_view(), name='chat-history'),

    # JWT Authentication Endpoints (SimpleJWT)
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Custom Auth Actions (from AuthViewSet)
    path('auth/login/', AuthViewSet.as_view({'post': 'login'}), name='jwt_login'),
    path('auth/register/', AuthViewSet.as_view({'post': 'register'}), name='jwt_register'),
    path('auth/logout/', AuthViewSet.as_view({'post': 'logout'}), name='jwt_logout'),
    path('auth/me/', AuthViewSet.as_view({'get': 'me'}), name='jwt_me'),
    path("auth/accept-invite/", AcceptStaffInviteView.as_view(),name="accept-staff-invite"),
]

# =============================
# FINAL URLPATTERNS
# =============================
urlpatterns = router.urls + additional_patterns
