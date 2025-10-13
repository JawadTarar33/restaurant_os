import random
from datetime import datetime, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum

from restaurant_os.models import (
    User, Restaurant, Branch, MenuCategory, MenuItem,
    Customer, POSSale, POSSaleItem,
    DailySales, BranchDailySales,
    Supplier, InventoryItem, InventoryOrder
)

class Command(BaseCommand):
    help = "Generate realistic dummy data for all models for the past 90 days."

    def handle(self, *args, **kwargs):
        self.stdout.write("🔹 Starting dummy data generation...")
        start_date = timezone.now().date() - timedelta(days=90)
        end_date = timezone.now().date()

        # ============================
        # Create Users, Restaurant, Branches
        # ============================
        admin, _ = User.objects.get_or_create(
            email="admin@example.com",
            defaults={"role": "admin", "is_staff": True, "is_superuser": True, "full_name": "Admin User"}
        )
        owner, _ = User.objects.get_or_create(
            email="owner@example.com",
            defaults={"role": "owner", "is_staff": True, "full_name": "Restaurant Owner"}
        )

        restaurant, _ = Restaurant.objects.get_or_create(
            name="Gourmet Palace",
            owner=owner,
            defaults={"location": "Downtown"}
        )

        branches = []
        for city in ["Lahore", "Karachi", "Islamabad"]:
            branch, _ = Branch.objects.get_or_create(
                restaurant=restaurant,
                name=f"{city} Branch",
                defaults={
                    "city": city,
                    "address": f"Main Road {city}",
                    "phone": f"+92{random.randint(3000000000, 3999999999)}",
                    "manager": owner
                }
            )
            branches.append(branch)

        # ============================
        # Create Menu
        # ============================
        categories = []
        for cname in ["Starters", "Main Course", "Desserts", "Beverages"]:
            cat, _ = MenuCategory.objects.get_or_create(restaurant=restaurant, name=cname)
            categories.append(cat)

        menu_items = []
        for cat in categories:
            for i in range(5):
                item, _ = MenuItem.objects.get_or_create(
                    restaurant=restaurant,
                    category=cat,
                    name=f"{cat.name} Item {i+1}",
                    defaults={"price": Decimal(random.randint(150, 800))}
                )
                menu_items.append(item)

        # ============================
        # Create Customers
        # ============================
        customers = []
        for i in range(15):
            cust, _ = Customer.objects.get_or_create(
                contact=f"+92{random.randint(3000000000, 3999999999)}",
                defaults={
                    "name": f"Customer {i+1}",
                    "email": f"customer{i+1}@mail.com"
                }
            )
            customers.append(cust)

        # ============================
        # Create Suppliers and Inventory
        # ============================
        supplier, _ = Supplier.objects.get_or_create(
            restaurant=restaurant,
            name="FoodSupply Co.",
            defaults={"contact_person": "John Supplier", "phone": "+923009998877"}
        )

        inventory_items = []
        for name in ["Chicken", "Beef", "Flour", "Sugar", "Rice", "Spices"]:
            item, _ = InventoryItem.objects.get_or_create(
                restaurant=restaurant,
                supplier=supplier,
                name=name,
                defaults={
                    "quantity_in_stock": Decimal(random.randint(50, 200)),
                    "unit": "kg",
                    "reorder_level": Decimal(30),
                    "reorder_quantity": Decimal(100),
                    "last_restock_date": timezone.now().date()
                }
            )
            inventory_items.append(item)

        # ============================
        # Generate Daily Sales and POS Transactions
        # ============================
        with transaction.atomic():
            total_sales_created = 0
            for branch in branches:
                for n in range(90):
                    date = start_date + timedelta(days=n)

                    # Random transactions per day
                    num_sales = random.randint(10, 40)
                    branch_revenue = Decimal(0)

                    for _ in range(num_sales):
                        customer = random.choice(customers)
                        subtotal = Decimal(0)

                        sale = POSSale.objects.create(
                            branch=branch,
                            customer=customer,
                            cashier=owner,
                            payment_method=random.choice(["cash", "card", "digital"]),
                            subtotal=0,
                            tax_amount=0,
                            total=0,
                            discount_amount=0,
                            created_at=datetime.combine(date, datetime.min.time()),
                        )

                        for _ in range(random.randint(1, 4)):
                            item = random.choice(menu_items)
                            qty = random.randint(1, 3)
                            total_price = item.price * qty
                            tax = total_price * Decimal("0.08")
                            POSSaleItem.objects.create(
                                sale=sale,
                                menu_item=item,
                                quantity=qty,
                                unit_price=item.price,
                                tax_amount=tax,
                                total=total_price + tax
                            )
                            subtotal += total_price + tax

                        discount = subtotal * Decimal(random.uniform(0.05, 0.15))
                        total = subtotal - discount

                        sale.subtotal = subtotal
                        sale.tax_amount = subtotal * Decimal("0.08")
                        sale.discount_amount = discount
                        sale.total = total
                        sale.save()

                        branch_revenue += total
                        total_sales_created += 1

                    # Save daily summary
                    BranchDailySales.objects.update_or_create(
                        branch=branch,
                        date=date,
                        defaults={
                            "revenue": branch_revenue,
                            "transactions": num_sales,
                            "customer_footfall": num_sales * random.randint(1, 3),
                            "avg_ticket_size": branch_revenue / num_sales if num_sales else 0,
                            "discount_percentage": Decimal(random.uniform(5, 15))
                        }
                    )

            # Create restaurant-level daily totals
            for n in range(90):
                day_total = BranchDailySales.objects.filter(date=date).aggregate(
                    total=Sum("revenue"),
                    orders=Sum("transactions")
                )
                
                if day_total["total"]:
                    DailySales.objects.update_or_create(
                        restaurant=restaurant,
                        date=date,
                        defaults={
                            "total_sales": day_total["total"],
                            "total_orders": day_total["orders"] or 0,
                            "avg_order_value": (day_total["total"] / (day_total["orders"] or 1))
                        }
                    )

        # ============================
        # Generate Inventory Orders
        # ============================
        for _ in range(30):
            item = random.choice(inventory_items)
            InventoryOrder.objects.create(
                restaurant=restaurant,
                supplier=supplier,
                inventory_item=item,
                quantity_ordered=Decimal(random.randint(20, 80)),
                unit_price=Decimal(random.randint(100, 500)),
                status=random.choice(["pending", "ordered", "received"]),
                order_date=timezone.now() - timedelta(days=random.randint(1, 90))
            )

        self.stdout.write(self.style.SUCCESS(f"✅ Dummy data generation complete! Created {total_sales_created} sales."))
