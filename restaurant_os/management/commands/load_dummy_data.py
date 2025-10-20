# restaurant_os/management/commands/populate_database.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import random
from restaurant_os.models import (
    User, Restaurant, Branch, MenuCategory, MenuItem, Customer,
    POSSale, POSSaleItem, Supplier, InventoryItem, InventoryOrder,
    InventoryUsage, DailySales, BranchDailySales, RestaurantStaff
)


class Command(BaseCommand):
    help = 'Populates database with 3 months of realistic data'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Starting database population...'))
        
        # Clear existing data (optional - comment out if you want to keep existing data)
        self.stdout.write('Clearing existing data...')
        # POSSaleItem.objects.all().delete()
        # POSSale.objects.all().delete()
        # BranchDailySales.objects.all().delete()
        # DailySales.objects.all().delete()
        # Customer.objects.all().delete()
        # InventoryOrder.objects.all().delete()
        # InventoryUsage.objects.all().delete()
        # InventoryItem.objects.all().delete()
        # MenuItem.objects.all().delete()
        # MenuCategory.objects.all().delete()
        # Supplier.objects.all().delete()
        # RestaurantStaff.objects.all().delete()
        # Branch.objects.all().delete()
        # Restaurant.objects.all().delete()
        # User.objects.filter(is_superuser=False).delete()
        
        # Create data
        self.create_users()
        self.create_restaurants()
        self.create_branches()
        self.create_suppliers()
        self.create_menu_categories()
        self.create_menu_items()
        self.create_inventory_items()
        self.create_inventory_usage()
        self.create_customers()
        self.create_pos_sales()  # This will also create BranchDailySales
        self.create_inventory_orders()
        
        self.stdout.write(self.style.SUCCESS('Database population completed!'))

    def create_users(self):
        self.stdout.write('Creating users...')
        
        # Create owner
        self.owner = User.objects.get_or_create(
            email='owner@restaurant.com',
            defaults={
                'full_name': 'John Malik',
                'phone': '+92-300-1234567',
                'role': 'owner',
                'is_active': True
            }
        )[0]
        self.owner.set_password('password123')
        self.owner.save()
        
        # Create managers
        self.managers = []
        manager_names = ['Ahmed Khan', 'Sara Iqbal', 'Bilal Shah', 'Ayesha Noor']
        for i, name in enumerate(manager_names):
            manager = User.objects.get_or_create(
                email=f'manager{i+1}@restaurant.com',
                defaults={
                    'full_name': name,
                    'phone': f'+92-300-{2000000+i}',
                    'role': 'manager',
                    'is_active': True
                }
            )[0]
            manager.set_password('password123')
            manager.save()
            self.managers.append(manager)
        
        # Create staff
        self.staff = []
        staff_names = ['Ali Raza', 'Fatima Malik', 'Hassan Ahmed', 'Zainab Khan', 
                       'Usman Ali', 'Maryam Siddiqui', 'Kamran Haider', 'Nida Farooq']
        for i, name in enumerate(staff_names):
            staff = User.objects.get_or_create(
                email=f'staff{i+1}@restaurant.com',
                defaults={
                    'full_name': name,
                    'phone': f'+92-300-{3000000+i}',
                    'role': 'staff',
                    'is_active': True
                }
            )[0]
            staff.set_password('password123')
            staff.save()
            self.staff.append(staff)
        
        self.stdout.write(self.style.SUCCESS(f'Created {len(self.managers)} managers and {len(self.staff)} staff'))

    def create_restaurants(self):
        self.stdout.write('Creating restaurants...')
        
        self.restaurant = Restaurant.objects.get_or_create(
            name='Taste of Pakistan',
            defaults={
                'location': 'Islamabad',
                'owner': self.owner
            }
        )[0]
        
        self.stdout.write(self.style.SUCCESS(f'Created restaurant: {self.restaurant.name}'))

    def create_branches(self):
        self.stdout.write('Creating branches...')
        
        branch_data = [
            {
                'name': 'F-7 Branch',
                'city': 'Islamabad',
                'address': 'Main Market, F-7 Markaz, Islamabad',
                'phone': '+92-51-2345678',
                'manager': self.managers[0]
            },
            {
                'name': 'Blue Area Branch',
                'city': 'Islamabad',
                'address': 'Jinnah Avenue, Blue Area, Islamabad',
                'phone': '+92-51-2345679',
                'manager': self.managers[1]
            },
            {
                'name': 'DHA Lahore Branch',
                'city': 'Lahore',
                'address': 'Y Block, DHA Phase 3, Lahore',
                'phone': '+92-42-3456789',
                'manager': self.managers[2]
            },
            {
                'name': 'Gulberg Branch',
                'city': 'Lahore',
                'address': 'Main Boulevard, Gulberg III, Lahore',
                'phone': '+92-42-3456790',
                'manager': self.managers[3]
            }
        ]
        
        self.branches = []
        for data in branch_data:
            branch = Branch.objects.get_or_create(
                restaurant=self.restaurant,
                name=data['name'],
                defaults=data
            )[0]
            self.branches.append(branch)
            
            # Assign staff to branches
            RestaurantStaff.objects.get_or_create(
                restaurant=self.restaurant,
                user=data['manager'],
                defaults={'role': 'manager'}
            )
        
        self.stdout.write(self.style.SUCCESS(f'Created {len(self.branches)} branches'))

    def create_suppliers(self):
        self.stdout.write('Creating suppliers...')
        
        supplier_data = [
            {
                'name': 'Metro Fresh Supplies',
                'contact_person': 'Imran Malik',
                'phone': '+92-300-4567890',
                'email': 'metro@supplies.com',
                'address': 'I-9 Industrial Area, Islamabad'
            },
            {
                'name': 'Green Valley Farms',
                'contact_person': 'Zahid Khan',
                'phone': '+92-300-4567891',
                'email': 'greenvalley@farms.com',
                'address': 'Rawalpindi'
            },
            {
                'name': 'Spice King',
                'contact_person': 'Abdullah Ahmed',
                'phone': '+92-300-4567892',
                'email': 'info@spiceking.com',
                'address': 'Anarkali Bazaar, Lahore'
            },
            {
                'name': 'Dairy Fresh',
                'contact_person': 'Asim Raza',
                'phone': '+92-300-4567893',
                'email': 'orders@dairyfresh.com',
                'address': 'Faisalabad'
            }
        ]
        
        self.suppliers = []
        for data in supplier_data:
            supplier = Supplier.objects.get_or_create(
                restaurant=self.restaurant,
                name=data['name'],
                defaults=data
            )[0]
            self.suppliers.append(supplier)
        
        self.stdout.write(self.style.SUCCESS(f'Created {len(self.suppliers)} suppliers'))

    def create_menu_categories(self):
        self.stdout.write('Creating menu categories...')
        
        categories = ['Appetizers', 'Main Course', 'BBQ & Grills', 'Breads', 
                     'Rice Dishes', 'Beverages', 'Desserts']
        
        self.categories = []
        for cat_name in categories:
            category = MenuCategory.objects.get_or_create(
                restaurant=self.restaurant,
                name=cat_name
            )[0]
            self.categories.append(category)
        
        self.stdout.write(self.style.SUCCESS(f'Created {len(self.categories)} categories'))

    def create_menu_items(self):
        self.stdout.write('Creating menu items...')
        
        menu_items = [
            # Appetizers
            ('Samosas', 'Appetizers', 150, 'Crispy fried samosas with spicy filling'),
            ('Spring Rolls', 'Appetizers', 180, 'Vegetable spring rolls'),
            ('Chicken Wings', 'Appetizers', 350, 'Spicy chicken wings'),
            
            # Main Course
            ('Chicken Karahi', 'Main Course', 850, 'Traditional chicken karahi'),
            ('Mutton Karahi', 'Main Course', 1200, 'Tender mutton karahi'),
            ('Palak Paneer', 'Main Course', 550, 'Spinach and cottage cheese'),
            ('Dal Makhani', 'Main Course', 450, 'Creamy black lentils'),
            ('Butter Chicken', 'Main Course', 900, 'Chicken in creamy tomato sauce'),
            
            # BBQ & Grills
            ('Chicken Tikka', 'BBQ & Grills', 650, 'Grilled chicken tikka'),
            ('Seekh Kabab', 'BBQ & Grills', 700, 'Minced meat kababs'),
            ('Malai Boti', 'BBQ & Grills', 750, 'Creamy chicken boti'),
            ('Beef Chapli Kabab', 'BBQ & Grills', 800, 'Traditional Chapli kabab'),
            
            # Breads
            ('Naan', 'Breads', 40, 'Plain naan'),
            ('Garlic Naan', 'Breads', 60, 'Naan with garlic'),
            ('Tandoori Roti', 'Breads', 30, 'Whole wheat tandoori roti'),
            ('Paratha', 'Breads', 50, 'Layered paratha'),
            
            # Rice Dishes
            ('Chicken Biryani', 'Rice Dishes', 450, 'Aromatic chicken biryani'),
            ('Mutton Biryani', 'Rice Dishes', 650, 'Spiced mutton biryani'),
            ('Vegetable Biryani', 'Rice Dishes', 350, 'Vegetable biryani'),
            ('Plain Rice', 'Rice Dishes', 200, 'Steamed basmati rice'),
            
            # Beverages
            ('Soft Drink', 'Beverages', 80, 'Chilled soft drink'),
            ('Fresh Lime', 'Beverages', 120, 'Fresh lime water'),
            ('Lassi', 'Beverages', 150, 'Traditional yogurt drink'),
            ('Green Tea', 'Beverages', 100, 'Hot green tea'),
            
            # Desserts
            ('Gulab Jamun', 'Desserts', 180, 'Sweet milk balls in syrup'),
            ('Kheer', 'Desserts', 200, 'Rice pudding'),
            ('Gajar Halwa', 'Desserts', 250, 'Carrot halwa'),
        ]
        
        self.menu_items = []
        for name, cat_name, price, desc in menu_items:
            category = next(c for c in self.categories if c.name == cat_name)
            item = MenuItem.objects.get_or_create(
                restaurant=self.restaurant,
                name=name,
                defaults={
                    'category': category,
                    'price': Decimal(str(price)),
                    'description': desc,
                    'available': True
                }
            )[0]
            self.menu_items.append(item)
        
        self.stdout.write(self.style.SUCCESS(f'Created {len(self.menu_items)} menu items'))

    def create_inventory_items(self):
        self.stdout.write('Creating inventory items...')
        
        inventory_data = [
            # Vegetables & Produce
            ('Onions', 50, 'kg', 10, 20, self.suppliers[1]),
            ('Tomatoes', 45, 'kg', 10, 20, self.suppliers[1]),
            ('Potatoes', 60, 'kg', 15, 30, self.suppliers[1]),
            ('Garlic', 25, 'kg', 5, 10, self.suppliers[1]),
            ('Ginger', 20, 'kg', 5, 10, self.suppliers[1]),
            ('Green Chilies', 15, 'kg', 5, 10, self.suppliers[1]),
            ('Coriander', 10, 'kg', 3, 5, self.suppliers[1]),
            
            # Meat & Protein
            ('Chicken', 80, 'kg', 20, 40, self.suppliers[0]),
            ('Mutton', 40, 'kg', 10, 20, self.suppliers[0]),
            ('Beef', 50, 'kg', 15, 30, self.suppliers[0]),
            
            # Dairy
            ('Milk', 100, 'liter', 20, 50, self.suppliers[3]),
            ('Yogurt', 50, 'liter', 10, 20, self.suppliers[3]),
            ('Cream', 30, 'liter', 8, 15, self.suppliers[3]),
            ('Butter', 25, 'kg', 5, 10, self.suppliers[3]),
            ('Paneer', 20, 'kg', 5, 10, self.suppliers[3]),
            
            # Spices
            ('Red Chili Powder', 30, 'kg', 5, 10, self.suppliers[2]),
            ('Turmeric', 20, 'kg', 5, 10, self.suppliers[2]),
            ('Cumin Seeds', 15, 'kg', 3, 8, self.suppliers[2]),
            ('Coriander Powder', 18, 'kg', 4, 8, self.suppliers[2]),
            ('Garam Masala', 12, 'kg', 3, 6, self.suppliers[2]),
            
            # Staples
            ('Rice (Basmati)', 150, 'kg', 30, 60, self.suppliers[0]),
            ('Flour (Atta)', 200, 'kg', 40, 80, self.suppliers[0]),
            ('Oil', 80, 'liter', 20, 40, self.suppliers[0]),
            ('Salt', 50, 'kg', 10, 20, self.suppliers[0]),
            ('Sugar', 60, 'kg', 15, 30, self.suppliers[0]),
        ]
        
        self.inventory_items = []
        for name, qty, unit, reorder_level, reorder_qty, supplier in inventory_data:
            item = InventoryItem.objects.get_or_create(
                restaurant=self.restaurant,
                name=name,
                defaults={
                    'quantity_in_stock': Decimal(str(qty)),
                    'unit': unit,
                    'reorder_level': Decimal(str(reorder_level)),
                    'reorder_quantity': Decimal(str(reorder_qty)),
                    'supplier': supplier,
                    'last_restock_date': timezone.now().date() - timedelta(days=random.randint(1, 15))
                }
            )[0]
            self.inventory_items.append(item)
        
        self.stdout.write(self.style.SUCCESS(f'Created {len(self.inventory_items)} inventory items'))

    def create_inventory_usage(self):
        self.stdout.write('Creating inventory usage relationships...')
        
        # Map menu items to inventory items with usage amounts
        usage_map = {
            'Chicken Karahi': [('Chicken', 0.5), ('Onions', 0.2), ('Tomatoes', 0.3), ('Oil', 0.1)],
            'Mutton Karahi': [('Mutton', 0.5), ('Onions', 0.2), ('Tomatoes', 0.3), ('Oil', 0.1)],
            'Chicken Biryani': [('Chicken', 0.4), ('Rice (Basmati)', 0.3), ('Onions', 0.15), ('Yogurt', 0.1)],
            'Mutton Biryani': [('Mutton', 0.4), ('Rice (Basmati)', 0.3), ('Onions', 0.15), ('Yogurt', 0.1)],
            'Butter Chicken': [('Chicken', 0.4), ('Butter', 0.05), ('Cream', 0.1), ('Tomatoes', 0.2)],
            'Palak Paneer': [('Paneer', 0.3), ('Onions', 0.1), ('Cream', 0.05)],
            'Chicken Tikka': [('Chicken', 0.5), ('Yogurt', 0.1), ('Garam Masala', 0.02)],
            'Naan': [('Flour (Atta)', 0.15), ('Milk', 0.05), ('Oil', 0.02)],
            'Garlic Naan': [('Flour (Atta)', 0.15), ('Garlic', 0.02), ('Milk', 0.05)],
        }
        
        count = 0
        for menu_name, ingredients in usage_map.items():
            menu_item = next((m for m in self.menu_items if m.name == menu_name), None)
            if not menu_item:
                continue
                
            for inv_name, qty in ingredients:
                inv_item = next((i for i in self.inventory_items if i.name == inv_name), None)
                if inv_item:
                    InventoryUsage.objects.get_or_create(
                        inventory_item=inv_item,
                        menu_item=menu_item,
                        defaults={'quantity_used_per_item': Decimal(str(qty))}
                    )
                    count += 1
        
        self.stdout.write(self.style.SUCCESS(f'Created {count} inventory usage relationships'))

    def create_customers(self):
        self.stdout.write('Creating customers...')
        
        first_names = ['Ahmed', 'Ali', 'Hassan', 'Usman', 'Bilal', 'Kamran', 'Imran', 'Fahad',
                       'Sara', 'Ayesha', 'Fatima', 'Zainab', 'Maryam', 'Nida', 'Sana', 'Hina']
        last_names = ['Khan', 'Ahmed', 'Ali', 'Shah', 'Malik', 'Hussain', 'Iqbal', 'Raza']
        
        self.customers = []
        for i in range(100):
            name = f"{random.choice(first_names)} {random.choice(last_names)}"
            contact = f"03{random.randint(10, 49)}{random.randint(1000000, 9999999)}"
            
            customer = Customer.objects.create(
                name=name,
                contact=contact,
                email=f"{name.lower().replace(' ', '.')}@email.com" if random.random() > 0.3 else None
            )
            self.customers.append(customer)
        
        self.stdout.write(self.style.SUCCESS(f'Created {len(self.customers)} customers'))

    def create_pos_sales(self):
        self.stdout.write('Creating POS sales for the past 3 months...')
        
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=150)
        
        # Track daily sales for aggregation
        daily_sales_tracker = {}
        
        total_sales = 0
        current_date = start_date
        
        while current_date <= end_date:
            # Determine day type for sales volume
            is_weekend = current_date.weekday() in [4, 5]  # Friday, Saturday
            is_friday = current_date.weekday() == 4  # Friday (biggest day in Pakistan)
            
            for branch in self.branches:
                # Base target: ~50 sales per day with realistic variations
                # Weekend boost and natural fluctuations
                if is_friday:
                    base_sales = random.randint(60, 75)  # Friday rush
                elif is_weekend:
                    base_sales = random.randint(55, 68)  # Saturday busy
                else:
                    base_sales = random.randint(42, 58)  # Weekday average
                
                # Add positive growth trend over 3 months (5-10% growth)
                days_passed = (current_date - start_date).days
                growth_factor = 1 + (days_passed / 1200)  # ~7.5% growth over 90 days
                
                # Add seasonal/weekly variations (±5%)
                week_variation = 1 + (random.uniform(-0.05, 0.05))
                
                daily_sales_count = int(base_sales * growth_factor * week_variation)
                
                # Track for BranchDailySales
                day_key = (branch.id, current_date)
                if day_key not in daily_sales_tracker:
                    daily_sales_tracker[day_key] = {
                        'revenue': Decimal('0'),
                        'transactions': 0,
                        'discount_total': Decimal('0')
                    }
                
                # Create sales for this day
                for _ in range(daily_sales_count):
                    # Random time during business hours (11 AM to 11 PM)
                    hour = random.randint(11, 22)
                    minute = random.randint(0, 59)
                    sale_time = timezone.make_aware(
                        datetime.combine(current_date, datetime.min.time()).replace(hour=hour, minute=minute)
                    )
                    
                    # Select random customer (80% returning customers)
                    customer = random.choice(self.customers) if random.random() > 0.2 else None
                    
                    # Select random cashier
                    cashier = random.choice(self.staff)
                    
                    # Payment method distribution
                    payment_method = random.choices(
                        ['cash', 'card', 'digital'],
                        weights=[0.5, 0.3, 0.2]
                    )[0]
                    
                    # Select 1-5 random items
                    num_items = random.choices([1, 2, 3, 4, 5], weights=[0.2, 0.35, 0.25, 0.15, 0.05])[0]
                    selected_items = random.sample(self.menu_items, num_items)
                    
                    # Calculate totals
                    subtotal = Decimal('0')
                    for item in selected_items:
                        quantity = random.randint(1, 3)
                        subtotal += item.price * quantity
                    
                    tax_amount = subtotal * Decimal('0.17')
                    
                    # Random discount (15% chance of discount)
                    discount_amount = Decimal('0')
                    if random.random() < 0.15:
                        discount_pct = random.choice([5, 10, 15, 20])
                        discount_amount = subtotal * Decimal(str(discount_pct / 100))
                    
                    total = subtotal + tax_amount - discount_amount
                    
                    # Create POS Sale
                    sale = POSSale.objects.create(
                        branch=branch,
                        customer=customer,
                        cashier=cashier,
                        payment_method=payment_method,
                        subtotal=subtotal,
                        tax_amount=tax_amount,
                        discount_amount=discount_amount,
                        total=total,
                        created_at=sale_time
                    )
                    
                    # Create sale items
                    for item in selected_items:
                        quantity = random.randint(1, 3)
                        unit_price = item.price
                        item_subtotal = unit_price * quantity
                        item_tax = item_subtotal * Decimal('0.17')
                        item_total = item_subtotal + item_tax
                        
                        POSSaleItem.objects.create(
                            sale=sale,
                            menu_item=item,
                            quantity=quantity,
                            unit_price=unit_price,
                            tax_amount=item_tax,
                            total=item_total
                        )
                    
                    # Update daily tracker
                    daily_sales_tracker[day_key]['revenue'] += total
                    daily_sales_tracker[day_key]['transactions'] += 1
                    daily_sales_tracker[day_key]['discount_total'] += discount_amount
                    
                    total_sales += 1
            
            current_date += timedelta(days=1)
            
            # Progress indicator
            if total_sales % 500 == 0:
                self.stdout.write(f'  Created {total_sales} sales...')
        
        # Create BranchDailySales records
        self.stdout.write('Creating BranchDailySales aggregates...')
        for (branch_id, date), data in daily_sales_tracker.items():
            revenue = data['revenue']
            transactions = data['transactions']
            discount_total = data['discount_total']
            
            avg_ticket = revenue / transactions if transactions > 0 else Decimal('0')
            discount_pct = (discount_total / revenue * 100) if revenue > 0 else Decimal('0')
            customer_footfall = int(transactions * Decimal('1.2'))  # Estimate footfall
            
            BranchDailySales.objects.create(
                branch_id=branch_id,
                date=date,
                revenue=revenue,
                transactions=transactions,
                customer_footfall=customer_footfall,
                avg_ticket_size=avg_ticket,
                discount_percentage=discount_pct
            )
        
        self.stdout.write(self.style.SUCCESS(
            f'Created {total_sales} POS sales and {len(daily_sales_tracker)} daily sales records'
        ))

    def create_inventory_orders(self):
        self.stdout.write('Creating inventory orders...')
        
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=90)
        
        count = 0
        current_date = start_date
        
        while current_date <= end_date:
            # Create 2-5 orders per week
            if current_date.weekday() in [0, 3]:  # Monday and Thursday
                num_orders = random.randint(2, 5)
                
                for _ in range(num_orders):
                    inv_item = random.choice(self.inventory_items)
                    
                    # Determine status based on date
                    days_old = (end_date - current_date).days
                    if days_old > 7:
                        status = 'received'
                        received_date = current_date + timedelta(days=random.randint(2, 7))
                    elif days_old > 3:
                        status = random.choice(['ordered', 'received'])
                        received_date = current_date + timedelta(days=random.randint(2, 5)) if status == 'received' else None
                    else:
                        status = random.choice(['pending', 'ordered'])
                        received_date = None
                    
                    order_time = timezone.make_aware(
                        datetime.combine(current_date, datetime.min.time()).replace(hour=10, minute=0)
                    )
                    
                    InventoryOrder.objects.create(
                        restaurant=self.restaurant,
                        supplier=inv_item.supplier,
                        inventory_item=inv_item,
                        quantity_ordered=inv_item.reorder_quantity,
                        unit_price=Decimal(str(random.uniform(50, 500))),
                        status=status,
                        order_date=order_time,
                        received_date=timezone.make_aware(
                            datetime.combine(received_date, datetime.min.time())
                        ) if received_date else None
                    )
                    count += 1
            
            current_date += timedelta(days=1)
        
        self.stdout.write(self.style.SUCCESS(f'Created {count} inventory orders'))