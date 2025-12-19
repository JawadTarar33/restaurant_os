# ===============================
# views.py - COMPLETE WITH ALL VIEWSETS
# ===============================
from django.db import transaction 
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from django.db.models import Sum, Avg, Count, F, Q
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal
from .models import *
from .serializers import *
from .ml_service import MLService
from rest_framework.views import APIView
import requests
from django.conf import settings
import traceback
from rest_framework.parsers import MultiPartParser, FormParser
ml_service = MLService()


# ===============================
# CUSTOM PERMISSIONS
# ===============================
class IsOwner(IsAuthenticated):
    """Only restaurant owners can access"""
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.role == 'owner'


class IsOwnerOrAssignedStaff(IsAuthenticated):
    """Owner sees all, staff sees only their assigned branch"""
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.role in ['owner', 'staff', 'manager']
# ===============================
# HELPER MIXIN FOR ACCESS CONTROL
# ===============================
class BranchAccessMixin:
    """Mixin to provide branch access control methods"""
    
    def get_accessible_branches(self, user=None):
        """Get all branches user can access"""
        user = user or self.request.user
        
        if user.role == 'owner':
            return Branch.objects.filter(restaurant__owner=user, is_active=True)
        elif user.role in ['staff', 'manager']:
            return user.assigned_branches.filter(is_active=True)
        
        return Branch.objects.none()
    
    def check_branch_access(self, branch_id, user=None):
        """Check if user has access to specific branch"""
        user = user or self.request.user
        
        if user.role == 'owner':
            return Branch.objects.filter(
                id=branch_id,
                restaurant__owner=user
            ).exists()
        elif user.role in ['staff', 'manager']:
            return user.assigned_branches.filter(id=branch_id).exists()
        
        return False
    
    def get_accessible_restaurants(self, user=None):
        """Get all restaurants user can access"""
        user = user or self.request.user
        
        if user.role == 'owner':
            return Restaurant.objects.filter(owner=user, is_active=True)
        elif user.role in ['staff', 'manager']:
            restaurant_ids = user.assigned_branches.values_list('restaurant_id', flat=True).distinct()
            return Restaurant.objects.filter(id__in=restaurant_ids, is_active=True)
        
        return Restaurant.objects.none()

# ===============================
# AUTHENTICATION
# ===============================

class AuthViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    @action(detail=False, methods=['post'])
    def register(self, request):
        """Owner registration only - staff must be invited"""
        email = request.data.get('email')
        password = request.data.get('password')
        full_name = request.data.get('full_name')
        role = request.data.get('role', 'owner')

        if not email or not password or not full_name:
            return Response({
                'status': 'error',
                'message': 'Email, password, and full_name are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        if role != 'owner':
            return Response({
                'status': 'error',
                'message': 'Only restaurant owners can self-register. Staff must be invited by the owner.'
            }, status=status.HTTP_403_FORBIDDEN)

        if User.objects.filter(email=email).exists():
            return Response({
                'status': 'error',
                'message': 'User with this email already exists'
            }, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(
            email=email,
            password=password,
            full_name=full_name,
            role='owner'
        )

        refresh = RefreshToken.for_user(user)

        return Response({
            'status': 'success',
            'message': 'Owner account created successfully.',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def login(self, request):
        """JWT-based user login"""
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response({
                'status': 'error',
                'message': 'Email and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email=email).first()

        if not user or not user.check_password(password):
            return Response({
                'status': 'error',
                'message': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)

        refresh = RefreshToken.for_user(user)

        # Gather assigned branches and restaurants
        assigned_branches, accessible_restaurants = [], []
        if user.role == 'owner':
            restaurants = Restaurant.objects.filter(owner=user)
            accessible_restaurants = list(restaurants.values('id', 'name'))
            branches = Branch.objects.filter(restaurant__owner=user, is_active=True)
            assigned_branches = list(branches.values('id', 'branch_name', 'restaurant__name', 'city'))
        elif user.role in ['staff', 'manager']:
            assigned_branches = list(
                user.assigned_branches.filter(is_active=True).values(
                    'id', 'branch_name', 'restaurant__name', 'city', 'restaurant_id'
                )
            )
            restaurant_ids = user.assigned_branches.values_list('restaurant_id', flat=True).distinct()
            accessible_restaurants = list(
                Restaurant.objects.filter(id__in=restaurant_ids).values('id', 'name')
            )

        return Response({
            'status': 'success',
            'message': 'Login successful',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
            'assigned_branches': assigned_branches,
            'accessible_restaurants': accessible_restaurants,
            'permissions': {
                'can_create_restaurant': user.role == 'owner',
                'can_create_branch': user.role == 'owner',
                'role': user.role
            }
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        """Blacklist refresh token"""
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            return Response({
                "status": "error",
                "message": "Refresh token is required to logout"
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({
                "status": "success",
                "message": "Logged out successfully"
            }, status=status.HTTP_200_OK)
        except TokenError as e:
            return Response({
                "status": "error",
                "message": f"Token error: {str(e)}"
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                "status": "error",
                "message": "Invalid or expired token"
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """Get current user info"""
        assigned_branches = []
        if request.user.role in ['staff', 'manager']:
            assigned_branches = list(
                request.user.assigned_branches.values('id', 'branch_name', 'restaurant__name')
            )

        return Response({
            'status': 'success',
            'user': UserSerializer(request.user).data,
            'assigned_branches': assigned_branches
        }, status=status.HTTP_200_OK)
    
# ===============================
# RESTAURANT MANAGEMENT (OWNER ONLY)
# ===============================

class RestaurantViewSet(viewsets.ModelViewSet, BranchAccessMixin):
    queryset = Restaurant.objects.all()
    serializer_class = RestaurantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Owner sees their restaurants, staff sees restaurants of assigned branches"""
        user = self.request.user
        if user.role == 'owner':
            return Restaurant.objects.filter(owner=user, is_active=True)
        elif user.role in ['staff', 'manager']:
            restaurant_ids = user.assigned_branches.values_list('restaurant_id', flat=True).distinct()
            return Restaurant.objects.filter(id__in=restaurant_ids, is_active=True)
        return Restaurant.objects.none()

    def create(self, request, *args, **kwargs):
        """Allow only one restaurant per owner"""
        user = request.user

        if user.role != 'owner':
            return Response({
                'error': 'Only restaurant owners can create restaurants'
            }, status=403)

        # Check if the owner already has a restaurant
        if Restaurant.objects.filter(owner=user, is_active=True).exists():
            return Response({
                'error': 'You already have a restaurant. Each owner can create only one.'
            }, status=400)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(owner=user)

        return Response({
            'message': 'Restaurant created successfully',
            'restaurant': serializer.data
        }, status=201)


    def update(self, request, *args, **kwargs):
        """Only owner can update their restaurant"""
        instance = self.get_object()
        if request.user.role != 'owner' or instance.owner != request.user:
            return Response({
                'error': 'You can only update your own restaurant'
            }, status=403)
        
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Soft delete - mark as inactive"""
        instance = self.get_object()
        if request.user.role != 'owner' or instance.owner != request.user:
            return Response({
                'error': 'You can only delete your own restaurant'
            }, status=403)
        
        instance.is_active = False
        instance.save()
        return Response({
            'message': 'Restaurant deactivated successfully'
        })


    @action(detail=True, methods=['get'])
    def staff_list(self, request, pk=None):
        """Get all staff members for this restaurant"""
        if request.user.role != 'owner':
            return Response({'error': 'Only owners can view staff list'}, status=403)
        
        restaurant = self.get_object()
        if restaurant.owner != request.user:
            return Response({'error': 'Access denied'}, status=403)

        # Get all staff assigned to this restaurant's branches
        branch_ids = restaurant.branches.values_list('id', flat=True)
        staff = User.objects.filter(
            assigned_branches__id__in=branch_ids,
            role__in=['staff', 'manager']
        ).distinct()

        staff_data = []
        for user in staff:
            assigned = user.assigned_branches.filter(restaurant=restaurant).values('id', 'name')
            staff_data.append({
                'id': user.id,
                'email': user.email,
                'full_name': user.full_name,
                'role': user.role,
                'assigned_branches': list(assigned),
                'is_active': user.is_active
            })

        return Response({
            'restaurant': restaurant.name,
            'staff_count': len(staff_data),
            'staff': staff_data
        })

    @action(detail=True, methods=['patch'])
    def update_staff_branches(self, request, pk=None):
        """Update staff member's assigned branches"""
        if request.user.role != 'owner':
            return Response({'error': 'Only owners can update staff assignments'}, status=403)
        
        restaurant = self.get_object()
        if restaurant.owner != request.user:
            return Response({'error': 'Access denied'}, status=403)

        staff_id = request.data.get('staff_id')
        branch_ids = request.data.get('branch_ids', [])

        if not staff_id:
            return Response({'error': 'staff_id is required'}, status=400)

        staff_user = User.objects.filter(
            id=staff_id,
            role__in=['staff', 'manager']
        ).first()

        if not staff_user:
            return Response({'error': 'Staff member not found'}, status=404)

        # Verify branches belong to this restaurant
        valid_branches = Branch.objects.filter(
            id__in=branch_ids,
            restaurant=restaurant
        )

        staff_user.assigned_branches.set(valid_branches)

        return Response({
            'message': 'Staff assignments updated',
            'staff': staff_user.full_name,
            'assigned_branches': list(valid_branches.values('id', 'name'))
        })

# ===============================
# BRANCH MANAGEMENT
# ===============================

class BranchViewSet(viewsets.ModelViewSet, BranchAccessMixin):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    permission_classes = [IsAuthenticated]

# ----------------------------------------------------------------
    # LIST: Retrieve all accessible branches
    # ----------------------------------------------------------------
    def list(self, request, *args, **kwargs):
        """Return branches accessible to the user"""
        user = request.user
        if user.role == 'owner':
            branches = Branch.objects.filter(restaurant__owner=user, is_active=True)
        elif user.role in ['manager', 'staff']:
            branches = self.get_accessible_branches().filter(is_active=True)
        else:
            branches = Branch.objects.none()

        serializer = self.get_serializer(branches, many=True)
        return Response(serializer.data, status=200)

    # ----------------------------------------------------------------
    # CREATE: Owners create new branches
    # ----------------------------------------------------------------
    def create(self, request, *args, **kwargs):
        """Only restaurant owners can create branches"""
        user = request.user
        if user.role != 'owner':
            return Response({'error': 'Only restaurant owners can create branches'}, status=403)

        restaurant_id = request.data.get('restaurant')
        if not restaurant_id:
            return Response({'error': 'restaurant field is required'}, status=400)

        restaurant = Restaurant.objects.filter(id=restaurant_id, owner=user, is_active=True).first()
        if not restaurant:
            return Response({'error': 'Restaurant not found or you do not own it'}, status=404)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(restaurant=restaurant)

        return Response({
            'message': 'Branch created successfully',
            'branch': serializer.data
        }, status=201)

    # ----------------------------------------------------------------
    # RETRIEVE: via body instead of URL
    # ----------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def get_branch(self, request):
        """Retrieve single branch via ID in body"""
        branch_id = request.data.get('id')
        if not branch_id:
            return Response({'error': 'Branch id is required'}, status=400)

        branch = Branch.objects.filter(id=branch_id, is_active=True).first()
        if not branch:
            return Response({'error': 'Branch not found'}, status=404)

        # Access control
        if not self.check_branch_access(branch.id):
            return Response({'error': 'Access denied to this branch'}, status=403)

        serializer = self.get_serializer(branch)
        return Response(serializer.data, status=200)

    # ----------------------------------------------------------------
    # UPDATE: via body instead of URL
    # ----------------------------------------------------------------
    @action(detail=False, methods=['patch'])
    def update_branch(self, request):
        """Update a branch via ID in body (owner only)"""
        user = request.user
        branch_id = request.data.get('id')

        if not branch_id:
            return Response({'error': 'Branch id is required'}, status=400)

        branch = Branch.objects.filter(id=branch_id, is_active=True).first()
        if not branch:
            return Response({'error': 'Branch not found'}, status=404)

        if user.role != 'owner' or branch.restaurant.owner != user:
            return Response({'error': 'Only the restaurant owner can update this branch'}, status=403)

        serializer = self.get_serializer(branch, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            'message': 'Branch updated successfully',
            'branch': serializer.data
        }, status=200)

    # ----------------------------------------------------------------
    # DELETE: via body instead of URL
    # ----------------------------------------------------------------
    @action(detail=False, methods=['delete'])
    def delete_branch(self, request):
        """Soft delete branch via ID in body (owner only)"""
        user = request.user
        branch_id = request.data.get('id')

        if not branch_id:
            return Response({'error': 'Branch id is required'}, status=400)

        branch = Branch.objects.filter(id=branch_id, is_active=True).first()
        if not branch:
            return Response({'error': 'Branch not found'}, status=404)

        if user.role != 'owner' or branch.restaurant.owner != user:
            return Response({'error': 'Access denied'}, status=403)

        branch.is_active = False
        branch.save(update_fields=['is_active'])

        return Response({'message': 'Branch deactivated successfully'}, status=200)
    
    @action(detail=True, methods=['get'])
    def weekly_summary(self, request, pk=None):
        """Get weekly sales summary for branch"""
        branch = self.get_object()
        
        if not self.check_branch_access(branch.id):
            return Response({'error': 'Access denied to this branch'}, status=403)

        today = timezone.now().date()
        week_ago = today - timedelta(days=7)

        summary = BranchDailySales.objects.filter(
            branch=branch,
            date__gte=week_ago
        ).aggregate(
            total_revenue=Sum('revenue'),
            total_transactions=Sum('transactions'),
            avg_ticket=Avg('avg_ticket_size'),
            total_footfall=Sum('customer_footfall')
        )

        return Response({
            'branch': branch.name,
            'period': f'{week_ago} to {today}',
            'total_revenue': float(summary['total_revenue'] or 0),
            'total_transactions': summary['total_transactions'] or 0,
            'avg_ticket_size': float(summary['avg_ticket'] or 0),
            'total_footfall': summary['total_footfall'] or 0
        })

    @action(detail=True, methods=['get'])
    def staff_members(self, request, pk=None):
        """Get staff assigned to this branch"""
        branch = self.get_object()
        
        if not self.check_branch_access(branch.id):
            return Response({'error': 'Access denied'}, status=403)

        staff = branch.staff_members.filter(is_active=True)
        
        return Response({
            'branch': branch.name,
            'staff_count': staff.count(),
            'staff': UserSerializer(staff, many=True).data
        })


#User Management

class UserManagementViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"])
    def create_user(self, request):
        """
        Owner → create manager or staff
        Manager → create staff (only for own branch)
        """
        creator = request.user

        email = request.data.get("email")
        password = request.data.get("password")
        full_name = request.data.get("full_name")
        role = request.data.get("role")
        branch_ids = request.data.get("branch_ids", [])

        if not all([email, password, full_name, role, branch_ids]):
            return Response(
                {"error": "email, password, full_name, role, branch_ids required"},
                status=400
            )

        # 🔒 ROLE PERMISSIONS
        if creator.role == "manager" and role != "staff":
            return Response(
                {"error": "Managers can only create staff"},
                status=403
            )

        if creator.role not in ["owner", "manager"]:
            return Response(
                {"error": "Permission denied"},
                status=403
            )

        # 🔒 BRANCH SCOPE
        if creator.role == "manager":
            allowed_branch_ids = list(
                creator.assigned_branches.values_list("id", flat=True)
            )
            if set(branch_ids) != set(allowed_branch_ids):
                return Response(
                    {"error": "Manager can assign staff only to their own branch"},
                    status=403
                )

        # OWNER validation
        if creator.role == "owner":
            valid_branches = Branch.objects.filter(
                id__in=branch_ids,
                restaurant__owner=creator,
                is_active=True
            )
        else:
            valid_branches = creator.assigned_branches.filter(
                id__in=branch_ids,
                is_active=True
            )

        if valid_branches.count() != len(branch_ids):
            return Response(
                {"error": "Invalid branch assignment"},
                status=400
            )

        if User.objects.filter(email=email).exists():
            return Response(
                {"error": "User with this email already exists"},
                status=400
            )

        # ✅ CREATE USER
        user = User.objects.create_user(
            email=email,
            password=password,
            full_name=full_name,
            role=role
        )

        user.assigned_branches.set(valid_branches)

        return Response(
            {
                "message": "User created successfully",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role,
                    "assigned_branches": list(
                        valid_branches.values("id", "branch_name", "city")
                    )
                }
            },
            status=201
        )
    
    @action(detail=False, methods=["patch"])
    def update_user(self, request):
        editor = request.user
        user_id = request.data.get("user_id")
        branch_ids = request.data.get("branch_ids")

        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({"error": "User not found"}, status=404)

        # MANAGER RULES
        if editor.role == "manager":
            if user.role != "staff":
                return Response({"error": "Managers can only edit staff"}, status=403)

            if not editor.assigned_branches.filter(
                id__in=user.assigned_branches.values_list("id", flat=True)
            ).exists():
                return Response({"error": "Access denied"}, status=403)

        # OWNER RULES
        if editor.role == "owner":
            valid_branches = Branch.objects.filter(
                id__in=branch_ids,
                restaurant__owner=editor
            )
        else:
            valid_branches = editor.assigned_branches

        user.assigned_branches.set(valid_branches)

        return Response({"message": "User updated successfully"})
    
    @action(detail=False, methods=["delete"])
    def delete_user(self, request):
        deleter = request.user
        user_id = request.data.get("user_id")

        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({"error": "User not found"}, status=404)

        if deleter.role == "manager":
            if user.role != "staff":
                return Response({"error": "Managers can only delete staff"}, status=403)

            if not deleter.assigned_branches.filter(
                id__in=user.assigned_branches.values_list("id", flat=True)
            ).exists():
                return Response({"error": "Access denied"}, status=403)

        if deleter.role != "owner" and deleter.role != "manager":
            return Response({"error": "Permission denied"}, status=403)

        user.delete()
        return Response({"message": "User deleted successfully"})





# ===============================
# CATEGORY MANAGEMENT
# ===============================

class CategoryViewSet(viewsets.ModelViewSet, BranchAccessMixin):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter categories by accessible restaurants"""
        restaurants = self.get_accessible_restaurants()
        return Category.objects.filter(restaurant__in=restaurants, is_active=True)

    def list(self, request, *args, **kwargs):
        """Fetch all categories"""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "status": "success",
            "message": "Categories fetched successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        """Create a new category — only for owners"""
        if request.user.role != 'owner':
            return Response({
                "status": "error",
                "message": "Only restaurant owners can create categories"
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Validation failed",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()

        return Response({
            "status": "success",
            "message": "Category created successfully",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['patch'])
    def update_category(self, request):
        """Update a category (id passed in body)"""
        category_id = request.data.get("id")
        if not category_id:
            return Response({
                "status": "error",
                "message": "Category ID is required"
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            category = Category.objects.get(id=category_id, is_active=True)
        except Category.DoesNotExist:
            return Response({
                "status": "error",
                "message": "Category not found"
            }, status=status.HTTP_404_NOT_FOUND)

        # Check ownership
        if request.user.role != 'owner' or category.restaurant.owner != request.user:
            return Response({
                "status": "error",
                "message": "You can only update your own restaurant's categories"
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(category, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Validation failed",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()

        return Response({
            "status": "success",
            "message": "Category updated successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['delete'])
    def delete_category(self, request):
        """Soft delete a category (id passed in body)"""
        category_id = request.data.get("id")
        if not category_id:
            return Response({
                "status": "error",
                "message": "Category ID is required"
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            category = Category.objects.get(id=category_id, is_active=True)
        except Category.DoesNotExist:
            return Response({
                "status": "error",
                "message": "Category not found"
            }, status=status.HTTP_404_NOT_FOUND)

        if request.user.role != 'owner' or category.restaurant.owner != request.user:
            return Response({
                "status": "error",
                "message": "You can only delete your own restaurant's categories"
            }, status=status.HTTP_403_FORBIDDEN)

        category.is_active = False
        category.save()

        return Response({
            "status": "success",
            "message": "Category deleted successfully"
        }, status=status.HTTP_200_OK)

# ===============================
# MENU ITEMS
# ===============================
class MenuItemViewSet(viewsets.ModelViewSet, BranchAccessMixin):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    permission_classes = [IsAuthenticated]

    parser_classes = (MultiPartParser, FormParser)

    def get_queryset(self):
        restaurants = self.get_accessible_restaurants()
        queryset = MenuItem.objects.filter(restaurant__in=restaurants)

        category_id = self.request.query_params.get("category_id")
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        restaurant_id = self.request.query_params.get("restaurant")
        if restaurant_id:
            queryset = queryset.filter(restaurant_id=restaurant_id)

        return queryset

    def create(self, request, *args, **kwargs):
        if request.user.role != "owner":
            return Response({"error": "Only owners can create menu items"}, status=403)

        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=["put", "patch"])
    def update_item(self, request):
        item_id = request.data.get("id")
        if not item_id:
            return Response({"error": "id required"}, status=400)

        try:
            item = MenuItem.objects.get(id=item_id, restaurant__owner=request.user)
        except MenuItem.DoesNotExist:
            return Response({"error": "Not found or access denied"}, status=404)

        serializer = self.get_serializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            "status": "success",
            "message": "Item updated successfully",
            "data": serializer.data
        })

    @action(detail=False, methods=['post'])
    def get_item(self, request):
        item_id = request.data.get('id')
        if not item_id:
            return Response({'error': 'id is required'}, status=400)
        try:
            item = MenuItem.objects.get(id=item_id)
        except MenuItem.DoesNotExist:
            return Response({'error': 'Menu item not found'}, status=404)

        serializer = self.get_serializer(item, context={'request': request})
        return Response(serializer.data, status=200)


    @action(detail=False, methods=['delete', 'post'])
    def delete_item(self, request):
        item_id = request.data.get('id')
        if not item_id:
            return Response({'error': 'id is required'}, status=400)
        try:
            item = MenuItem.objects.get(id=item_id, restaurant__owner=request.user)
        except MenuItem.DoesNotExist:
            return Response({'error': 'Menu item not found or access denied'}, status=404)
        item.delete()
        return Response({'status': 'success', 'message': 'Menu item deleted successfully'}, status=200)

    @action(detail=False, methods=['post', 'delete'])
    def delete_multiple(self, request):
        item_ids = request.data.get('ids')
        if not isinstance(item_ids, list) or not item_ids:
            return Response({'error': 'ids must be a non-empty list'}, status=400)

        with transaction.atomic():
            items = MenuItem.objects.filter(id__in=item_ids, restaurant__owner=request.user)
            if not items.exists():
                return Response({'error': 'No matching menu items found or access denied'}, status=404)
            deleted_count = items.count()
            items.delete()

        return Response({'status': 'success', 'message': f'{deleted_count} menu items deleted successfully'}, status=200)

    @action(detail=False, methods=['patch'])
    def toggle_availability(self, request):
        if request.user.role != 'owner':
            return Response({'error': 'Only owners can toggle menu items'}, status=403)

        item_id = request.data.get('id')
        if not item_id:
            return Response({'error': 'id is required'}, status=400)

        try:
            item = MenuItem.objects.get(id=item_id, restaurant__owner=request.user)
        except MenuItem.DoesNotExist:
            return Response({'error': 'Menu item not found or access denied'}, status=404)

        item.available = not item.available
        # Map property to status field, we already implemented property setter
        item.save(update_fields=['status'])

        return Response({
            'status': 'success',
            'message': f'Item {"enabled" if item.available else "disabled"} successfully',
            'data': {'id': str(item.id), 'available': item.available}
        }, status=200)

# ===============================
# CUSTOMER MANAGEMENT
# ===============================
class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """All authenticated users can see customers"""
        return Customer.objects.all().order_by('-created_at')

    @action(detail=True, methods=['get'])
    def order_history(self, request, pk=None):
        """Get customer's order history"""
        customer = self.get_object()
        
        # Filter orders by accessible branches
        accessible_branches = BranchAccessMixin().get_accessible_branches(request.user)
        orders = POSSale.objects.filter(
            customer=customer,
            branch__in=accessible_branches
        ).order_by('-created_at')[:20]
        
        return Response({
            'customer': customer.name,
            'total_orders': orders.count(),
            'orders': POSSaleSerializer(orders, many=True).data
        })
# ===============================
# POS SYSTEM
# ===============================
class POSViewSet(viewsets.ViewSet, BranchAccessMixin):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def menu_items(self, request):
        """Get menu items for POS - requires branch_id"""
        branch_id = request.query_params.get('branch_id')
        
        if not branch_id:
            return Response({'error': 'branch_id is required'}, status=400)
        
        if not self.check_branch_access(branch_id):
            return Response({
                'error': 'Access denied to this branch'
            }, status=403)

        branch = Branch.objects.get(id=branch_id)
        items = MenuItem.objects.filter(
            restaurant=branch.restaurant,
            available=True
        ).select_related('category')

        data = []
        for item in items:
            tax = item.price * (branch.restaurant.tax_rate / 100)
            
            # Check inventory availability
            in_stock = True
            if hasattr(item, 'recipe') and item.recipe.is_active:
                in_stock, _ = item.recipe.check_availability(1)
            
            data.append({
                'id': item.id,
                'name': item.name,
                'description': item.description,
                'price': float(item.price),
                'tax_rate': float(branch.restaurant.tax_rate),
                'tax_amount': float(tax),
                'price_with_tax': float(item.price + tax),
                'category': item.category.name if item.category else 'Other',
                'category_id': item.category.id if item.category else None,
                'image': item.image,
                'in_stock': in_stock,
                'preparation_time': item.preparation_time,
                'last_modified': item.updated_at.isoformat()
            })

        return Response({
            'branch': {
                'id': branch.id,
                'name': branch.name,
                'restaurant': branch.restaurant.name,
                'tax_rate': float(branch.restaurant.tax_rate),
                'currency': branch.restaurant.currency
            },
            'items': data,
            'total_items': len(data),
            'timestamp': timezone.now().isoformat()
        })

    @action(detail=False, methods=['post'])
    def create_sale(self, request):
        """Create a POS sale"""
        serializer = CreatePOSSaleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        data = serializer.validated_data
        branch_id = request.data.get('branch_id')
        
        if not branch_id:
            return Response({'error': 'branch_id is required'}, status=400)

        # Check access
        if not self.check_branch_access(branch_id):
            return Response({
                'error': 'Access denied. You can only create sales for your assigned branch.'
            }, status=403)

        skip_inventory_check = request.data.get('skip_inventory_check', False)

        try:
            with transaction.atomic():
                branch = Branch.objects.get(id=branch_id)
                
                # Create or get customer
                customer, _ = Customer.objects.get_or_create(
                    contact=data['customer_contact'],
                    defaults={'name': data['customer_name']}
                )

                subtotal = Decimal('0')
                tax_total = Decimal('0')
                sale_items = []
                tax_rate = branch.restaurant.tax_rate / 100

                # Check inventory availability
                if not skip_inventory_check:
                    for item_data in data['items']:
                        menu_item = MenuItem.objects.get(id=item_data['menu_item_id'])
                        quantity = item_data['quantity']
                        
                        if hasattr(menu_item, 'recipe') and menu_item.recipe.is_active:
                            is_available, missing = menu_item.recipe.check_availability(quantity)
                            
                            if not is_available:
                                return Response({
                                    'error': 'Insufficient inventory',
                                    'item': menu_item.name,
                                    'missing_ingredients': missing
                                }, status=400)

                # Calculate totals
                for item_data in data['items']:
                    menu_item = MenuItem.objects.get(id=item_data['menu_item_id'], restaurant=branch.restaurant)
                    quantity = item_data['quantity']
                    unit_price = menu_item.price
                    item_subtotal = unit_price * quantity
                    item_tax = item_subtotal * Decimal(str(tax_rate))
                    item_total = item_subtotal + item_tax

                    subtotal += item_subtotal
                    tax_total += item_tax

                    sale_items.append({
                        'menu_item': menu_item,
                        'quantity': quantity,
                        'unit_price': unit_price,
                        'tax_amount': item_tax,
                        'total': item_total
                    })

                total = subtotal + tax_total - data['discount_amount']

                # Create sale
                sale = POSSale.objects.create(
                    branch=branch,
                    customer=customer,
                    cashier=request.user,
                    payment_method=data['payment_method'],
                    subtotal=subtotal,
                    tax_amount=tax_total,
                    discount_amount=data['discount_amount'],
                    total=total,
                    offline_sale_id=request.data.get('offline_sale_id')
                )

                # Create sale items
                for item in sale_items:
                    POSSaleItem.objects.create(
                        sale=sale,
                        menu_item=item['menu_item'],
                        quantity=item['quantity'],
                        unit_price=item['unit_price'],
                        tax_amount=item['tax_amount'],
                        total=item['total']
                    )

                # Process inventory
                success, result = sale.process_inventory_deductions()
                
                if not success:
                    raise ValueError(result)

                return Response({
                    'sale_id': sale.id,
                    'branch': branch.name,
                    'cashier': request.user.full_name,
                    'customer': customer.name,
                    'subtotal': float(subtotal),
                    'tax_amount': float(tax_total),
                    'discount': float(data['discount_amount']),
                    'total': float(total),
                    'payment_method': data['payment_method'],
                    'items_count': len(sale_items),
                    'message': 'Sale created successfully',
                    'inventory_deductions': result,
                    'created_at': sale.created_at.isoformat()
                }, status=201)

        except MenuItem.DoesNotExist:
            return Response({'error': 'One or more menu items not found'}, status=400)
        except Branch.DoesNotExist:
            return Response({'error': 'Branch not found'}, status=404)
        except Exception as e:
            return Response({'error': str(e)}, status=400)
         
    @action(detail=False, methods=['post'])
    def bulk_sync_sales(self, request):
        """Sync multiple offline sales at once"""
        sales_data = request.data.get('sales', [])
        
        if not sales_data:
            return Response({'error': 'No sales data provided'}, status=400)

        results = {
            'successful': [],
            'failed': []
        }

        for sale_data in sales_data:
            try:
                # Check branch access
                branch_id = sale_data.get('branch_id')
                if not self.check_branch_access(branch_id):
                    results['failed'].append({
                        'offline_id': sale_data.get('offline_sale_id'),
                        'error': 'Access denied to branch'
                    })
                    continue

                # Create sale
                serializer = CreatePOSSaleSerializer(data=sale_data)
                if not serializer.is_valid():
                    results['failed'].append({
                        'offline_id': sale_data.get('offline_sale_id'),
                        'error': serializer.errors
                    })
                    continue

                # Reuse create_sale logic
                with transaction.atomic():
                    data = serializer.validated_data
                    branch = Branch.objects.get(id=branch_id)
                    
                    customer, _ = Customer.objects.get_or_create(
                        contact=data['customer_contact'],
                        defaults={'name': data['customer_name']}
                    )

                    subtotal = Decimal('0')
                    tax_total = Decimal('0')
                    tax_rate = branch.restaurant.tax_rate / 100

                    for item_data in data['items']:
                        menu_item = MenuItem.objects.get(id=item_data['menu_item_id'])
                        quantity = item_data['quantity']
                        unit_price = menu_item.price
                        item_subtotal = unit_price * quantity
                        item_tax = item_subtotal * Decimal(str(tax_rate))
                        subtotal += item_subtotal
                        tax_total += item_tax

                    total = subtotal + tax_total - data['discount_amount']

                    sale = POSSale.objects.create(
                        branch=branch,
                        customer=customer,
                        cashier=request.user,
                        payment_method=data['payment_method'],
                        subtotal=subtotal,
                        tax_amount=tax_total,
                        discount_amount=data['discount_amount'],
                        total=total,
                        offline_sale_id=sale_data.get('offline_sale_id')
                    )

                    for item_data in data['items']:
                        menu_item = MenuItem.objects.get(id=item_data['menu_item_id'])
                        quantity = item_data['quantity']
                        unit_price = menu_item.price
                        item_subtotal = unit_price * quantity
                        item_tax = item_subtotal * Decimal(str(tax_rate))
                        item_total = item_subtotal + item_tax

                        POSSaleItem.objects.create(
                            sale=sale,
                            menu_item=menu_item,
                            quantity=quantity,
                            unit_price=unit_price,
                            tax_amount=item_tax,
                            total=item_total
                        )

                    sale.process_inventory_deductions()

                    results['successful'].append({
                        'offline_id': sale_data.get('offline_sale_id'),
                        'sale_id': sale.id,
                        'total': float(total)
                    })

            except Exception as e:
                results['failed'].append({
                    'offline_id': sale_data.get('offline_sale_id'),
                    'error': str(e)
                })

        return Response({
            'synced': len(results['successful']),
            'failed': len(results['failed']),
            'results': results,
            'message': f"Synced {len(results['successful'])} sales, {len(results['failed'])} failed"
        })

    @action(detail=False, methods=['get'])
    def recent_sales(self, request):
        """Get recent sales for accessible branches"""
        branch_id = request.query_params.get('branch_id')
        limit = int(request.query_params.get('limit', 20))

        accessible_branches = self.get_accessible_branches()
        
        sales = POSSale.objects.filter(branch__in=accessible_branches)
        
        if branch_id:
            if not self.check_branch_access(branch_id):
                return Response({'error': 'Access denied'}, status=403)
            sales = sales.filter(branch_id=branch_id)

        sales = sales.select_related('branch', 'customer', 'cashier').order_by('-created_at')[:limit]

        return Response({
            'sales': POSSaleSerializer(sales, many=True).data,
            'count': sales.count()
        })
# ===============================
# FINANCE DASHBOARD
# ===============================
class FinanceDashboardViewSet(viewsets.ViewSet, BranchAccessMixin):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def branch_overview(self, request):
        """Get financial overview for a specific branch"""
        branch_id = request.query_params.get('branch_id')
        
        if not branch_id:
            return Response({'error': 'branch_id is required'}, status=400)

        if not self.check_branch_access(branch_id):
            return Response({'error': 'Access denied to this branch'}, status=403)

        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        # Today's stats
        today_stats = POSSale.objects.filter(
            branch_id=branch_id,
            created_at__date=today
        ).aggregate(
            revenue=Sum('total'),
            transactions=Count('id'),
            avg_ticket=Avg('total')
        )

        # Week stats
        week_stats = POSSale.objects.filter(
            branch_id=branch_id,
            created_at__date__gte=week_ago
        ).aggregate(
            total_revenue=Sum('total'),
            total_transactions=Count('id'),
            avg_ticket=Avg('total'),
            total_tax=Sum('tax_amount'),
            total_discount=Sum('discount_amount')
        )

        # Month stats
        month_stats = POSSale.objects.filter(
            branch_id=branch_id,
            created_at__date__gte=month_ago
        ).aggregate(
            revenue=Sum('total'),
            transactions=Count('id')
        )

        # Daily breakdown for last 7 days
        daily = []
        for i in range(7):
            date = today - timedelta(days=i)
            day_sales = POSSale.objects.filter(
                branch_id=branch_id,
                created_at__date=date
            ).aggregate(revenue=Sum('total'), count=Count('id'))

            daily.append({
                'date': str(date),
                'revenue': float(day_sales['revenue'] or 0),
                'transactions': day_sales['count'] or 0
            })

        # Payment method breakdown
        payment_methods = POSSale.objects.filter(
            branch_id=branch_id,
            created_at__date__gte=week_ago
        ).values('payment_method').annotate(
            total=Sum('total'),
            count=Count('id')
        )

        branch = Branch.objects.get(id=branch_id)

        return Response({
            'branch': {
                'id': branch.id,
                'name': branch.name,
                'city': branch.city,
                'restaurant': branch.restaurant.name
            },
            'today': {
                'revenue': float(today_stats['revenue'] or 0),
                'transactions': today_stats['transactions'] or 0,
                'avg_ticket': float(today_stats['avg_ticket'] or 0)
            },
            'week': {
                'revenue': float(week_stats['total_revenue'] or 0),
                'transactions': week_stats['total_transactions'] or 0,
                'avg_ticket': float(week_stats['avg_ticket'] or 0),
                'tax_collected': float(week_stats['total_tax'] or 0),
                'discounts_given': float(week_stats['total_discount'] or 0)
            },
            'month': {
                'revenue': float(month_stats['revenue'] or 0),
                'transactions': month_stats['transactions'] or 0
            },
            'daily_breakdown': daily,
            'payment_methods': list(payment_methods)
        })

    @action(detail=False, methods=['get'])
    def all_branches(self, request):
        """Get overview of all accessible branches"""
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)

        branches = self.get_accessible_branches()
        
        data = []
        total_revenue = 0
        total_transactions = 0

        for branch in branches:
            stats = POSSale.objects.filter(
                branch=branch,
                created_at__date__gte=week_ago
            ).aggregate(
                revenue=Sum('total'),
                transactions=Count('id'),
                avg_ticket=Avg('total')
            )

            revenue = float(stats['revenue'] or 0)
            total_revenue += revenue
            total_transactions += stats['transactions'] or 0

            data.append({
                'branch_id': branch.id,
                'branch_name': branch.name,
                'city': branch.city,
                'restaurant': branch.restaurant.name,
                'revenue': revenue,
                'transactions': stats['transactions'] or 0,
                'avg_ticket': float(stats['avg_ticket'] or 0),
                'access_level': 'full' if request.user.role == 'owner' else 'assigned'
            })

        # Sort by revenue
        data.sort(key=lambda x: x['revenue'], reverse=True)

        return Response({
            'branches': data,
            'summary': {
                'total_branches': len(data),
                'total_revenue': total_revenue,
                'total_transactions': total_transactions,
                'avg_revenue_per_branch': total_revenue / len(data) if data else 0
            },
            'user_role': request.user.role,
            'period': f'{week_ago} to {today}'
        })

    @action(detail=False, methods=['get'])
    def top_selling_items(self, request):
        """Get top selling menu items"""
        branch_id = request.query_params.get('branch_id')
        days = int(request.query_params.get('days', 7))
        limit = int(request.query_params.get('limit', 10))

        accessible_branches = self.get_accessible_branches()
        
        query = POSSaleItem.objects.filter(
            sale__branch__in=accessible_branches,
            sale__created_at__date__gte=timezone.now().date() - timedelta(days=days)
        )

        if branch_id:
            if not self.check_branch_access(branch_id):
                return Response({'error': 'Access denied'}, status=403)
            query = query.filter(sale__branch_id=branch_id)

        top_items = query.values(
            'menu_item__name',
            'menu_item__id'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('total'),
            times_ordered=Count('id')
        ).order_by('-total_quantity')[:limit]

        return Response({
            'period_days': days,
            'items': list(top_items)
        })

    @action(detail=False, methods=['post'])
    def sync_daily_sales(self, request):
        """Admin/Owner: Rebuild BranchDailySales from POSSale records"""
        if request.user.role not in ['owner', 'admin'] and not request.user.is_superuser:
            return Response({'error': 'Permission denied'}, status=403)

        try:
            accessible_branches = self.get_accessible_branches()
            
            # Get unique dates from sales
            sale_dates = POSSale.objects.filter(
                branch__in=accessible_branches
            ).dates('created_at', 'day', order='DESC')

            total_created = 0

            for sale_date in sale_dates:
                for branch in accessible_branches:
                    daily_sales = POSSale.objects.filter(
                        branch=branch,
                        created_at__date=sale_date
                    )
                    
                    if daily_sales.exists():
                        aggregates = daily_sales.aggregate(
                            total_revenue=Sum('total'),
                            total_discount=Sum('discount_amount')
                        )

                        total_revenue = aggregates['total_revenue'] or Decimal('0')
                        total_discount = aggregates['total_discount'] or Decimal('0')
                        total_transactions = daily_sales.count()
                        avg_ticket = (total_revenue / total_transactions) if total_transactions > 0 else Decimal('0')
                        discount_pct = (total_discount / total_revenue * 100) if total_revenue > 0 else Decimal('0')

                        BranchDailySales.objects.update_or_create(
                            branch=branch,
                            date=sale_date,
                            defaults={
                                'revenue': total_revenue,
                                'transactions': total_transactions,
                                'customer_footfall': int(total_transactions * Decimal('1.2')),
                                'avg_ticket_size': avg_ticket,
                                'discount_percentage': discount_pct
                            }
                        )
                        total_created += 1

            return Response({
                'message': f'Successfully synced {total_created} BranchDailySales records.',
                'branches_processed': accessible_branches.count(),
                'dates_processed': sale_dates.count()
            })

        except Exception as e:
            return Response({
                'error': str(e),
                'traceback': traceback.format_exc()
            }, status=500)
# ===============================
# SALES ANALYTICS
# ===============================
class SalesAnalyticsViewSet(viewsets.ViewSet, BranchAccessMixin):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def branch_sales(self, request):
        """Get detailed sales analytics for branches"""
        branch_id = request.query_params.get('branch_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        accessible_branches = self.get_accessible_branches()
        query = BranchDailySales.objects.filter(branch__in=accessible_branches)
        
        if branch_id:
            if not self.check_branch_access(branch_id):
                return Response({'error': 'Access denied'}, status=403)
            query = query.filter(branch_id=branch_id)
        
        if start_date and end_date:
            query = query.filter(date__range=[start_date, end_date])

        serializer = BranchDailySalesSerializer(query, many=True)
        return Response({
            'analytics': serializer.data,
            'count': query.count()
        })

    @action(detail=False, methods=['get'])
    def compare_periods(self, request):
        """Compare two time periods"""
        branch_id = request.query_params.get('branch_id')
        
        if not branch_id:
            return Response({'error': 'branch_id required'}, status=400)
        
        if not self.check_branch_access(branch_id):
            return Response({'error': 'Access denied'}, status=403)

        today = timezone.now().date()
        
        # Current week
        current_week_start = today - timedelta(days=7)
        current_week = POSSale.objects.filter(
            branch_id=branch_id,
            created_at__date__gte=current_week_start
        ).aggregate(
            revenue=Sum('total'),
            transactions=Count('id')
        )

        # Previous week
        previous_week_start = today - timedelta(days=14)
        previous_week_end = today - timedelta(days=7)
        previous_week = POSSale.objects.filter(
            branch_id=branch_id,
            created_at__date__gte=previous_week_start,
            created_at__date__lt=previous_week_end
        ).aggregate(
            revenue=Sum('total'),
            transactions=Count('id')
        )

        current_revenue = float(current_week['revenue'] or 0)
        previous_revenue = float(previous_week['revenue'] or 0)
        
        revenue_change = 0
        if previous_revenue > 0:
            revenue_change = ((current_revenue - previous_revenue) / previous_revenue) * 100

        return Response({
            'current_week': {
                'revenue': current_revenue,
                'transactions': current_week['transactions'] or 0
            },
            'previous_week': {
                'revenue': previous_revenue,
                'transactions': previous_week['transactions'] or 0
            },
            'comparison': {
                'revenue_change_percent': round(revenue_change, 2),
                'revenue_change_amount': current_revenue - previous_revenue,
                'trend': 'up' if revenue_change > 0 else 'down' if revenue_change < 0 else 'stable'
            }
        })

    @action(detail=False, methods=['get'])
    def sales_filter(self, request):
        date_str = request.query_params.get("date")
        item_id = request.query_params.get("item_id")
        branch_id = request.query_params.get("branch_id")

        accessible_branches = self.get_accessible_branches()

        qs = POSSaleItem.objects.filter(sale__branch__in=accessible_branches)

        if date_str:
            qs = qs.filter(sale__created_at__date=date_str)

        if branch_id:
            if not self.check_branch_access(branch_id):
                return Response({"error": "Access denied"}, status=403)
            qs = qs.filter(sale__branch_id=branch_id)

        if item_id:
            qs = qs.filter(menu_item_id=item_id)

        results = qs.values(
            "menu_item__id",
            "menu_item__name",
            "sale__branch__branch_name"
        ).annotate(
            total_quantity=Sum("quantity"),
            total_revenue=Sum("total")
        )

        return Response({"results": list(results)})

# ===============================
# AI FORECASTING
# ===============================
class AIForecastViewSet(viewsets.ViewSet, BranchAccessMixin):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def generate_forecast(self, request):
        """Generate AI forecast for a branch"""
        branch_id = request.data.get('branch_id')

        if not branch_id:
            return Response({'error': 'branch_id required'}, status=400)

        if not self.check_branch_access(branch_id):
            return Response({'error': 'Access denied'}, status=403)

        try:
            forecasts = ml_service.generate_weekly_forecast(branch_id)
            serializer = BranchForecastSerializer(forecasts, many=True)
            return Response({
                'forecasts': serializer.data,
                'branch_id': branch_id
            })
        except Exception as e:
            return Response({'error': str(e)}, status=500)

    @action(detail=False, methods=['get'])
    def all_branches_forecast(self, request):
        """Get forecasts for all accessible branches"""
        branches = self.get_accessible_branches()
        
        results = []
        today = timezone.now().date()

        for branch in branches:
            latest = BranchForecast.objects.filter(
                branch=branch,
                forecast_date__gte=today
            ).first()

            if latest:
                results.append({
                    'branch_id': branch.id,
                    'branch_name': branch.name,
                    'city': branch.city,
                    'restaurant': branch.restaurant.name,
                    'predicted_revenue': float(latest.predicted_revenue),
                    'predicted_growth': float(latest.predicted_growth),
                    'confidence': latest.confidence_score,
                    'factors': latest.factors,
                    'forecast_date': str(latest.forecast_date),
                    'message': f"{branch.name} is predicted to {'grow' if latest.predicted_growth > 0 else 'decline'} by {abs(float(latest.predicted_growth)):.1f}%"
                })

        return Response({
            'forecasts': results,
            'total_branches': len(results)
        })
# ===============================
# INVENTORY MANAGEMENT
# ===============================
class InventoryViewSet(viewsets.ModelViewSet, BranchAccessMixin):
    queryset = InventoryItem.objects.all()
    serializer_class = InventoryItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter inventory by accessible restaurants"""
        restaurants = self.get_accessible_restaurants()
        branches = self.get_accessible_branches()
        return InventoryItem.objects.filter(branch__in=branches)


    def create(self, request, *args, **kwargs):
        """Only owner can add inventory items"""
        if request.user.role != 'owner':
            return Response({'error': 'Only owners can add inventory items'}, status=403)
        
        branch_id = request.data.get("branch")

        if not branch_id:
            return Response(
                {"error": "branch field is required"},
                status=400
            )

        branch = Branch.objects.filter(
            id=branch_id,
            restaurant__owner=request.user,
            is_active=True
        ).first()

        if not branch:
            return Response(
                {"error": "Invalid branch or access denied"},
                status=403
            )

        request.data["restaurant"] = branch.restaurant.id

        
        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Get low stock items"""
        query = self.get_queryset().filter(
            quantity_in_stock__lte=F('reorder_level')
        ).order_by('quantity_in_stock')
        
        serializer = self.get_serializer(query, many=True)
        return Response({
            'low_stock_items': serializer.data,
            'count': query.count(),
            'warning': 'These items need restocking'
        })

    @action(detail=True, methods=['post'])
    def adjust_stock(self, request, pk=None):
        """Adjust inventory stock"""
        item = self.get_object()
        
        if request.user.role not in ['owner', 'manager']:
            return Response({'error': 'Permission denied'}, status=403)

        adjustment = Decimal(str(request.data.get('adjustment', 0)))
        transaction_type = request.data.get('transaction_type', 'adjustment')
        notes = request.data.get('notes', '')

        if adjustment == 0:
            return Response({'error': 'Adjustment cannot be zero'}, status=400)

        old_quantity = item.quantity_in_stock
        item.quantity_in_stock += adjustment
        
        if item.quantity_in_stock < 0:
            return Response({'error': 'Stock cannot be negative'}, status=400)
        
        item.save()

        # Log transaction
        InventoryTransaction.objects.create(
            inventory_item=item,
            transaction_type=transaction_type,
            quantity=abs(adjustment),
            notes=notes,
            performed_by=request.user
        )

        return Response({
            'message': 'Stock adjusted successfully',
            'item': item.name,
            'old_quantity': float(old_quantity),
            'new_quantity': float(item.quantity_in_stock),
            'adjustment': float(adjustment)
        })
# ===============================
# RECIPES
# ===============================
class RecipeViewSet(viewsets.ModelViewSet, BranchAccessMixin):
    queryset = Recipe.objects.all()
    serializer_class = RecipeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter recipes by accessible restaurants"""
        restaurants = self.get_accessible_restaurants()
        return Recipe.objects.filter(menu_item__restaurant__in=restaurants)

    def create(self, request, *args, **kwargs):
        """Only owner can create recipes"""
        if request.user.role != 'owner':
            return Response({'error': 'Only owners can create recipes'}, status=403)
        
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['get'])
    def check_availability(self, request, pk=None):
        """Check if recipe ingredients are available"""
        recipe = self.get_object()
        quantity = int(request.query_params.get('quantity', 1))
        
        is_available, missing = recipe.check_availability(quantity)
        
        return Response({
            'available': is_available,
            'menu_item': recipe.menu_item.name,
            'quantity_requested': quantity,
            'missing_items': missing,
            'total_cost': float(recipe.get_total_cost() * quantity)
        })

    @action(detail=False, methods=['get'])
    def unavailable_items(self, request):
        """Get menu items that can't be made due to inventory"""
        unavailable = []
        
        for recipe in self.get_queryset().filter(is_active=True):
            is_available, missing = recipe.check_availability()
            
            if not is_available:
                unavailable.append({
                    'menu_item': recipe.menu_item.name,
                    'menu_item_id': recipe.menu_item.id,
                    'recipe_id': recipe.id,
                    'missing_ingredients': missing
                })
        
        return Response({
            'unavailable_items': unavailable,
            'count': len(unavailable)
        })



class IngredientViewSet(viewsets.ModelViewSet, BranchAccessMixin):
    queryset = RecipeIngredient.objects.all()
    serializer_class = RecipeIngredientWritableSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        restaurants = self.get_accessible_restaurants()
        return RecipeIngredient.objects.filter(
            recipe__menu_item__restaurant__in=restaurants
        )

# ===============================
# INVENTORY TRANSACTIONS
# ===============================
class InventoryTransactionViewSet(viewsets.ReadOnlyModelViewSet, BranchAccessMixin):
    queryset = InventoryTransaction.objects.all()
    serializer_class = InventoryTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter by accessible restaurants"""
        restaurants = self.get_accessible_restaurants()
        queryset = InventoryTransaction.objects.filter(
            inventory_item__restaurant__in=restaurants
        ).select_related('inventory_item', 'created_by')
        
        # Filters
        item_id = self.request.query_params.get('inventory_item_id')
        if item_id:
            queryset = queryset.filter(inventory_item_id=item_id)
        
        transaction_type = self.request.query_params.get('transaction_type')
        if transaction_type:
            queryset = queryset.filter(transaction_type=transaction_type)
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(created_at__date__range=[start_date, end_date])
        
        return queryset.order_by('-created_at')

    @action(detail=False, methods=['get'])
    def sales_impact(self, request):
        """Get inventory impact from sales"""
        days = int(request.query_params.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)
        
        restaurants = self.get_accessible_restaurants()
        
        impact = InventoryTransaction.objects.filter(
            transaction_type='sale',
            created_at__gte=start_date,
            inventory_item__restaurant__in=restaurants
        ).values(
            'inventory_item__name',
            'inventory_item__unit',
            'inventory_item__id'
        ).annotate(
            total_used=Sum('quantity')
        ).order_by('-total_used')[:20]
        
        return Response({
            'period_days': days,
            'items': list(impact),
            'count': len(impact)
        })
# ===============================
# SUPPLIERS
# ===============================
class SupplierViewSet(viewsets.ModelViewSet, BranchAccessMixin):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter suppliers by accessible restaurants"""
        restaurants = self.get_accessible_restaurants()
        return Supplier.objects.filter(restaurant__in=restaurants, is_active=True)

    def create(self, request, *args, **kwargs):
        """Only owner can add suppliers"""
        if request.user.role != 'owner':
            return Response({'error': 'Only owners can add suppliers'}, status=403)
        
        restaurant_id = request.data.get('restaurant_id')
        if not Restaurant.objects.filter(id=restaurant_id, owner=request.user).exists():
            return Response({'error': 'Invalid restaurant'}, status=400)
        
        return super().create(request, *args, **kwargs)
# ===============================
# INVENTORY ORDERS
# ===============================
class InventoryOrderViewSet(viewsets.ModelViewSet, BranchAccessMixin):
    queryset = InventoryOrder.objects.all()
    serializer_class = InventoryOrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter orders by accessible restaurants"""
        restaurants = self.get_accessible_restaurants()
        return InventoryOrder.objects.filter(branch__in=self.get_accessible_branches())


    def create(self, request, *args, **kwargs):
        """Create inventory order"""
        if request.user.role not in ['owner', 'manager']:
            return Response({'error': 'Permission denied'}, status=403)
        
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def mark_received(self, request, pk=None):
        """Mark order as received and update inventory"""
        order = self.get_object()
        
        if request.user.role not in ['owner', 'manager']:
            return Response({'error': 'Permission denied'}, status=403)

        if order.status == 'received':
            return Response({'error': 'Order already marked as received'}, status=400)

        order.status = 'received'
        order.save()

        return Response({
            'message': 'Order marked as received',
            'order_id': order.id,
            'supplier': order.supplier.name
        })
# ===============================
# AI CHAT INTERFACE
# ===============================
class AskAIView(APIView, BranchAccessMixin):
    """AI chat with access control"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_message = request.data.get("message")
        branch_id = request.data.get("branch_id")
        
        if not user_message:
            return Response(
                {"error": "message field is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify branch access if provided
        if branch_id and not self.check_branch_access(branch_id):
            return Response(
                {"error": "Access denied to this branch"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get accessible scope
        accessible_branch_ids = list(
            self.get_accessible_branches().values_list('id', flat=True)
        )
        accessible_restaurant_ids = list(
            self.get_accessible_restaurants().values_list('id', flat=True)
        )

        payload = {
            "user_id": request.user.id,
            "user_email": request.user.email,
            "user_role": request.user.role,
            "query": user_message,
            "branch_id": branch_id,
            "accessible_branch_ids": accessible_branch_ids,
            "accessible_restaurant_ids": accessible_restaurant_ids,
            "context": {
                "user_name": request.user.full_name or request.user.email,
                "timestamp": timezone.now().isoformat(),
                "access_scope": "all_branches" if request.user.role == 'owner' else "assigned_branches",
                "branch_count": len(accessible_branch_ids)
            }
        }

        try:
            response = requests.post(
                settings.N8N_WEBHOOK_URL,
                json=payload,
                headers={
                    'X-API-Key': settings.N8N_API_KEY,
                    'Content-Type': 'application/json'
                },
                timeout=120
            )
            
            response.raise_for_status()
            return Response(response.json(), status=response.status_code)
            
        except requests.exceptions.Timeout:
            return Response(
                {"error": "Request timed out. Please try again."},
                status=status.HTTP_504_GATEWAY_TIMEOUT
            )
        except requests.exceptions.RequestException as e:
            return Response(
                {"error": f"Failed to connect to AI service: {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
# ===============================
# RUN ML MODELS (FOR N8N)
# ===============================
class RunModelView(APIView, BranchAccessMixin):
    """Endpoint for n8n to call ML models"""
    permission_classes = [AllowAny]

    def post(self, request):
        # Verify API key
        api_key = request.headers.get('X-API-Key')
        if not hasattr(settings, 'N8N_API_KEY') or api_key != settings.N8N_API_KEY:
            return Response(
                {"error": "Unauthorized"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        model_type = request.data.get("model_type")
        branch_id = request.data.get("branch_id")

        if not model_type or not branch_id:
            return Response(
                {"error": "model_type and branch_id are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            if model_type == "forecast":
                forecasts = ml_service.generate_weekly_forecast(branch_id)
                return Response({
                    "status": "success",
                    "model_type": "forecast",
                    "branch_id": branch_id,
                    "results": BranchForecastSerializer(forecasts, many=True).data
                })

            elif model_type == "comparison":
                branch_2_id = request.data.get("branch_2_id")
                if not branch_2_id:
                    return Response(
                        {"error": "branch_2_id required for comparison"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                comparisons = ml_service.compare_branches_and_save(branch_id, branch_2_id)
                return Response({
                    "status": "success",
                    "model_type": "comparison",
                    "results": comparisons
                })

            elif model_type == "sales_prediction":
                # Custom prediction logic
                return Response({
                    "status": "success",
                    "model_type": "sales_prediction",
                    "message": "Implement your custom prediction model here"
                })

            else:
                return Response(
                    {"error": f"Unknown model_type: {model_type}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        except Exception as e:
            return Response(
                {"error": str(e), "traceback": traceback.format_exc()},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
# ===============================
# CHAT HISTORY (OPTIONAL)
# ===============================
class ChatHistoryView(APIView):
    """Store and retrieve chat history"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Implement based on your ChatMessage model
        return Response({
            "history": [],
            "message": "Chat history endpoint - implement based on your needs"
        })

    def post(self, request):
        # Store chat message
        return Response({
            "status": "saved",
            "message": "Chat message saved"
        })
# ===============================
# BRANCH COMPARISON (AI)
# ===============================
class AIComparisonViewSet(viewsets.ViewSet, BranchAccessMixin):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def compare_branches(self, request):
        """Compare two branches using AI"""
        branch_1_id = request.data.get('branch_1_id')
        branch_2_id = request.data.get('branch_2_id')

        if not branch_1_id or not branch_2_id:
            return Response({
                'error': 'Both branch_1_id and branch_2_id required'
            }, status=400)

        # Check access to both branches
        if not self.check_branch_access(branch_1_id) or not self.check_branch_access(branch_2_id):
            return Response({
                'error': 'Access denied to one or both branches'
            }, status=403)

        try:
            comparisons = ml_service.compare_branches_and_save(branch_1_id, branch_2_id)
            return Response({
                'comparison': comparisons,
                'branch_1_id': branch_1_id,
                'branch_2_id': branch_2_id
            })
        except Exception as e:
            return Response({'error': str(e)}, status=500)

    @action(detail=False, methods=['get'])
    def latest_comparisons(self, request):
        """Get recent branch comparisons"""
        accessible_branches = self.get_accessible_branches()
        
        today = timezone.now().date()
        comparisons = BranchComparison.objects.filter(
            Q(branch_1__in=accessible_branches) | Q(branch_2__in=accessible_branches),
            date=today
        )[:10]
        
        serializer = BranchComparisonSerializer(comparisons, many=True)
        return Response({
            'comparisons': serializer.data,
            'count': comparisons.count()
        })
# ===============================
# SYNC MANAGEMENT
# ===============================
class SyncManagementViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def log_sync_event(self, request):
        """Log sync events for monitoring"""
        event_type = request.data.get('event_type')
        details = request.data.get('details', {})
        
        # You can create a SyncLog model to track these
        return Response({
            'logged': True,
            'event_type': event_type,
            'timestamp': timezone.now().isoformat()
        })

    @action(detail=False, methods=['get'])
    def get_sync_stats(self, request):
        """Get sync statistics"""
        branch_id = request.query_params.get('branch_id')
        days = int(request.query_params.get('days', 7))
        
        if not branch_id:
            return Response({'error': 'branch_id required'}, status=400)

        # Check access
        if request.user.role == 'owner':
            has_access = Branch.objects.filter(
                id=branch_id,
                restaurant__owner=request.user
            ).exists()
        else:
            has_access = request.user.assigned_branches.filter(id=branch_id).exists()

        if not has_access:
            return Response({'error': 'Access denied'}, status=403)
        
        start_date = timezone.now().date() - timedelta(days=days)
        
        total_sales = POSSale.objects.filter(
            branch_id=branch_id,
            created_at__date__gte=start_date
        ).count()

        offline_sales = POSSale.objects.filter(
            branch_id=branch_id,
            created_at__date__gte=start_date,
            offline_sale_id__isnull=False
        ).count()

        return Response({
            'total_sales': total_sales,
            'offline_sales': offline_sales,
            'period_days': days,
            'branch_id': branch_id
        })
# ===============================
# REPORTS
# ===============================
class ReportsViewSet(viewsets.ViewSet, BranchAccessMixin):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def daily_sales_report(self, request):
        """Generate daily sales report"""
        branch_id = request.query_params.get('branch_id')
        date_str = request.query_params.get('date', str(timezone.now().date()))
        
        if not branch_id:
            return Response({'error': 'branch_id required'}, status=400)

        if not self.check_branch_access(branch_id):
            return Response({'error': 'Access denied'}, status=403)

        report_date = date.fromisoformat(date_str)
        
        sales = POSSale.objects.filter(
            branch_id=branch_id,
            created_at__date=report_date
        ).select_related('customer', 'cashier')

        summary = sales.aggregate(
            total_revenue=Sum('total'),
            total_transactions=Count('id'),
            cash_sales=Sum('total', filter=Q(payment_method='cash')),
            card_sales=Sum('total', filter=Q(payment_method='card')),
            mobile_sales=Sum('total', filter=Q(payment_method='mobile')),
            total_discounts=Sum('discount_amount'),
            total_tax=Sum('tax_amount')
        )

        # Top items sold
        top_items = POSSaleItem.objects.filter(
            sale__branch_id=branch_id,
            sale__created_at__date=report_date
        ).values('menu_item__name').annotate(
            quantity_sold=Sum('quantity'),
            revenue=Sum('total')
        ).order_by('-quantity_sold')[:10]

        branch = Branch.objects.get(id=branch_id)

        return Response({
            'date': str(report_date),
            'branch': {
                'id': branch.id,
                'name': branch.name,
                'restaurant': branch.restaurant.name
            },
            'summary': {
                'total_revenue': float(summary['total_revenue'] or 0),
                'total_transactions': summary['total_transactions'] or 0,
                'cash_sales': float(summary['cash_sales'] or 0),
                'card_sales': float(summary['card_sales'] or 0),
                'mobile_sales': float(summary['mobile_sales'] or 0),
                'total_discounts': float(summary['total_discounts'] or 0),
                'total_tax': float(summary['total_tax'] or 0)
            },
            'top_items': list(top_items),
            'sales_detail': POSSaleSerializer(sales, many=True).data
        })

    @action(detail=False, methods=['get'])
    def monthly_report(self, request):
        """Generate monthly report"""
        branch_id = request.query_params.get('branch_id')
        year = int(request.query_params.get('year', timezone.now().year))
        month = int(request.query_params.get('month', timezone.now().month))

        if not branch_id:
            return Response({'error': 'branch_id required'}, status=400)

        if not self.check_branch_access(branch_id):
            return Response({'error': 'Access denied'}, status=403)

        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)

        sales = POSSale.objects.filter(
            branch_id=branch_id,
            created_at__date__gte=start_date,
            created_at__date__lt=end_date
        )

        summary = sales.aggregate(
            total_revenue=Sum('total'),
            total_transactions=Count('id'),
            avg_ticket=Avg('total'),
            total_tax=Sum('tax_amount'),
            total_discounts=Sum('discount_amount')
        )

        # Daily breakdown
        daily_sales = []
        current_date = start_date
        while current_date < end_date:
            day_sales = sales.filter(created_at__date=current_date).aggregate(
                revenue=Sum('total'),
                transactions=Count('id')
            )
            daily_sales.append({
                'date': str(current_date),
                'revenue': float(day_sales['revenue'] or 0),
                'transactions': day_sales['transactions'] or 0
            })
            current_date += timedelta(days=1)

        branch = Branch.objects.get(id=branch_id)

        return Response({
            'period': f'{year}-{month:02d}',
            'branch': {
                'id': branch.id,
                'name': branch.name,
                'restaurant': branch.restaurant.name
            },
            'summary': {
                'total_revenue': float(summary['total_revenue'] or 0),
                'total_transactions': summary['total_transactions'] or 0,
                'avg_ticket': float(summary['avg_ticket'] or 0),
                'total_tax': float(summary['total_tax'] or 0),
                'total_discounts': float(summary['total_discounts'] or 0)
            },
            'daily_breakdown': daily_sales
        })
# ===============================
# USER MANAGEMENT
# ===============================
class UserManagementViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def profile(self, request):
        """Get user profile"""
        user = request.user
        
        assigned_branches = []
        if user.role in ['staff', 'manager']:
            assigned_branches = list(
                user.assigned_branches.values('id', 'name', 'restaurant__name', 'city')
            )

        restaurants = []
        if user.role == 'owner':
            restaurants = list(
                Restaurant.objects.filter(owner=user).values('id', 'name', 'is_active')
            )

        return Response({
            'user': UserSerializer(user).data,
            'assigned_branches': assigned_branches,
            'owned_restaurants': restaurants,
            'permissions': {
                'can_create_restaurant': user.role == 'owner',
                'can_create_branch': user.role == 'owner',
                'can_invite_staff': user.role == 'owner',
                'can_view_all_branches': user.role == 'owner'
            }
        })

    @action(detail=False, methods=['patch'])
    def update_profile(self, request):
        """Update user profile"""
        user = request.user
        
        full_name = request.data.get('full_name')
        if full_name:
            user.full_name = full_name
        
        # Don't allow role changes
        user.save()
        
        return Response({
            'message': 'Profile updated successfully',
            'user': UserSerializer(user).data
        })

    @action(detail=False, methods=['post'])
    def change_password(self, request):
        """Change user password"""
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')

        if not old_password or not new_password:
            return Response({
                'error': 'Both old_password and new_password are required'
            }, status=400)

        if not request.user.check_password(old_password):
            return Response({
                'error': 'Old password is incorrect'
            }, status=400)

        request.user.set_password(new_password)
        request.user.save()

        return Response({
            'message': 'Password changed successfully'
        })
# ===============================
# DASHBOARD STATS
# ===============================
class DashboardViewSet(viewsets.ViewSet, BranchAccessMixin):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Get dashboard overview"""
        accessible_branches = self.get_accessible_branches()
        today = timezone.now().date()

        # Today's stats
        today_sales = POSSale.objects.filter(
            branch__in=accessible_branches,
            created_at__date=today
        ).aggregate(
            revenue=Sum('total'),
            transactions=Count('id')
        )

        # This week
        week_ago = today - timedelta(days=7)
        week_sales = POSSale.objects.filter(
            branch__in=accessible_branches,
            created_at__date__gte=week_ago
        ).aggregate(
            revenue=Sum('total'),
            transactions=Count('id')
        )

        # Low stock items
        restaurants = self.get_accessible_restaurants()
        low_stock = InventoryItem.objects.filter(
            restaurant__in=restaurants,
            quantity_in_stock__lte=F('reorder_level')
        ).count()

        # Recent sales
        recent_sales = POSSale.objects.filter(
            branch__in=accessible_branches
        ).order_by('-created_at')[:5]

        return Response({
            'user': {
                'name': request.user.full_name,
                'role': request.user.role,
                'email': request.user.email
            },
            'today': {
                'revenue': float(today_sales['revenue'] or 0),
                'transactions': today_sales['transactions'] or 0
            },
            'this_week': {
                'revenue': float(week_sales['revenue'] or 0),
                'transactions': week_sales['transactions'] or 0
            },
            'alerts': {
                'low_stock_items': low_stock
            },
            'accessible_branches_count': accessible_branches.count(),
            'recent_sales': POSSaleSerializer(recent_sales, many=True).data
        })
