"""
Generate a multi-sheet Excel file with realistic synthetic data
for testing joins, relationships, and dynamic dashboards.

Tables & Relationships:
  customers (customer_id PK)
  products (product_id PK, category_id FK)
  categories (category_id PK)
  employees (employee_id PK, region_id FK)
  regions (region_id PK)
  orders (order_id PK, customer_id FK, employee_id FK)
  order_items (order_id FK, product_id FK)
  returns (return_id PK, order_id FK, product_id FK)
"""

import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

random.seed(42)

# ---------------------------------------------------------------------------
# 1. REGIONS
# ---------------------------------------------------------------------------
regions = [
    {"region_id": 1, "region_name": "North America", "country": "USA"},
    {"region_id": 2, "region_name": "North America", "country": "Canada"},
    {"region_id": 3, "region_name": "Europe", "country": "United Kingdom"},
    {"region_id": 4, "region_name": "Europe", "country": "Germany"},
    {"region_id": 5, "region_name": "Europe", "country": "France"},
    {"region_id": 6, "region_name": "Asia Pacific", "country": "Japan"},
    {"region_id": 7, "region_name": "Asia Pacific", "country": "Australia"},
    {"region_id": 8, "region_name": "Latin America", "country": "Brazil"},
    {"region_id": 9, "region_name": "Latin America", "country": "Mexico"},
    {"region_id": 10, "region_name": "Africa", "country": "South Africa"},
]
df_regions = pd.DataFrame(regions)

# ---------------------------------------------------------------------------
# 2. CATEGORIES & SUBCATEGORIES
# ---------------------------------------------------------------------------
categories = [
    {"category_id": 1, "category_name": "Electronics", "department": "Technology"},
    {"category_id": 2, "category_name": "Furniture", "department": "Home & Office"},
    {"category_id": 3, "category_name": "Clothing", "department": "Fashion"},
    {"category_id": 4, "category_name": "Office Supplies", "department": "Home & Office"},
    {"category_id": 5, "category_name": "Sports & Outdoors", "department": "Lifestyle"},
    {"category_id": 6, "category_name": "Books & Media", "department": "Entertainment"},
    {"category_id": 7, "category_name": "Food & Beverages", "department": "Consumables"},
    {"category_id": 8, "category_name": "Health & Beauty", "department": "Personal Care"},
]
df_categories = pd.DataFrame(categories)

# ---------------------------------------------------------------------------
# 3. PRODUCTS  (200 products)
# ---------------------------------------------------------------------------
product_names = {
    1: ["Laptop Pro 15", "Wireless Mouse", "USB-C Hub", "4K Monitor", "Mechanical Keyboard",
        "Bluetooth Speaker", "Noise-Cancel Headphones", "Webcam HD", "External SSD 1TB",
        "Tablet 10-inch", "Smart Watch", "Portable Charger", "LED Desk Lamp", "Surge Protector",
        "Graphics Card", "RAM Module 16GB", "Ethernet Cable 10m", "Wi-Fi Router",
        "VR Headset", "Drone Mini", "Action Camera", "E-Reader", "Projector Portable",
        "NAS Storage 4-Bay", "Thermal Printer"],
    2: ["Standing Desk", "Ergonomic Chair", "Bookshelf Oak", "Filing Cabinet", "Desk Lamp Classic",
        "Conference Table", "Sofa 3-Seater", "Coffee Table Glass", "Office Partition",
        "Whiteboard 120cm", "Bean Bag Chair", "TV Stand Modern", "Wall Shelf Set",
        "Dining Table Set", "Wardrobe 2-Door", "Shoe Rack", "Kitchen Island Cart",
        "Nightstand", "Mirror Full-Length", "Coat Rack", "Bar Stool Set",
        "Storage Ottoman", "Plant Stand", "Room Divider", "Desk Organizer Bamboo"],
    3: ["Cotton T-Shirt", "Denim Jeans", "Running Shoes", "Winter Jacket", "Silk Scarf",
        "Leather Belt", "Wool Sweater", "Linen Shirt", "Cargo Pants", "Sneakers Classic",
        "Rain Coat", "Baseball Cap", "Sunglasses Aviator", "Dress Formal", "Polo Shirt",
        "Hiking Boots", "Swim Trunks", "Yoga Pants", "Blazer Slim", "Beanie Knit",
        "Gloves Leather", "Socks Pack 6", "Sandals Comfort", "Hoodie Zip-Up", "Pajama Set"],
    4: ["A4 Paper 500-Pack", "Ballpoint Pens Box", "Sticky Notes Neon", "Stapler Heavy-Duty",
        "Binder Clips Set", "Whiteboard Markers", "Printer Ink Cartridge", "Envelope Pack 100",
        "Label Maker", "Paper Shredder", "Tape Dispenser", "Folder Set Color",
        "Clipboard Wood", "Rubber Bands Bag", "Calculator Scientific", "Planner 2025",
        "Notebook Spiral A5", "Index Cards Pack", "Pencil Case", "Hole Punch 3-Ring",
        "Correction Tape", "Desk Calendar", "Push Pins Box", "Scissors Titanium",
        "Glue Stick Pack"],
    5: ["Yoga Mat", "Dumbbells 10kg Pair", "Tennis Racket", "Camping Tent 4P",
        "Hiking Backpack 40L", "Bicycle Helmet", "Fishing Rod Set", "Soccer Ball Size 5",
        "Basketball Indoor", "Resistance Bands Set", "Jump Rope Speed", "Foam Roller",
        "Trekking Poles", "Swim Goggles", "Water Bottle 1L", "Golf Club Set",
        "Skateboard Complete", "Punching Bag", "Climbing Harness", "Kayak Paddle",
        "Running Vest LED", "Compression Sleeve", "Sports Watch GPS", "Bike Lock Heavy",
        "Cooler Bag 20L"],
    6: ["Python Programming Book", "Fantasy Novel Bestseller", "History Atlas",
        "Cookbook Mediterranean", "Self-Help Guide", "Vinyl Record Classic Rock",
        "Board Game Strategy", "Puzzle 1000 Pieces", "Documentary DVD Box",
        "Language Course Spanish", "Art Print Set", "Magazine Subscription Tech",
        "Audiobook Credits 3-Pack", "Sheet Music Collection", "Comic Anthology",
        "Travel Guide Europe", "Science Fiction Trilogy", "Children Book Set",
        "Graphic Novel Limited", "Poetry Collection", "Biography Bestseller",
        "Manga Volume 1", "Music Theory Book", "Film Blu-Ray Collector", "Coloring Book Adult"],
    7: ["Organic Coffee Beans 1kg", "Green Tea Box 100", "Protein Bars Pack 12",
        "Olive Oil Extra Virgin", "Dark Chocolate 85%", "Mixed Nuts 500g",
        "Energy Drink Case 24", "Dried Mango Slices", "Sparkling Water Pack 6",
        "Peanut Butter Crunchy", "Granola Bag 750g", "Honey Raw 500ml",
        "Coconut Water Pack 12", "Trail Mix Premium", "Matcha Powder 200g",
        "Kombucha Variety Pack", "Beef Jerky 300g", "Rice Cakes Pack", "Almond Milk 1L",
        "Hot Sauce Collection", "Maple Syrup Pure", "Dried Pasta 2kg",
        "Espresso Capsules 50", "Herbal Tea Sampler", "Superfood Blend Powder"],
    8: ["Moisturizer SPF 30", "Shampoo Organic", "Electric Toothbrush", "Vitamin D3 Bottle",
        "Face Mask Sheet Pack 10", "Deodorant Natural", "Hair Dryer Ionic",
        "Sunscreen SPF 50", "Lip Balm Trio", "Body Lotion 500ml", "Nail Polish Set",
        "Perfume Floral 50ml", "Razor Kit Premium", "Eye Cream Anti-Aging",
        "First Aid Kit", "Essential Oils Set", "Massage Gun", "Teeth Whitening Kit",
        "Cotton Pads 200", "Hand Sanitizer Pack", "Bath Bomb Set 6", "Protein Powder 1kg",
        "Collagen Supplement", "Sleep Mask Silk", "Scalp Massager"],
}

products = []
pid = 1
for cat_id, names in product_names.items():
    for name in names:
        cost = round(random.uniform(2.0, 300.0), 2)
        margin = random.uniform(0.15, 0.65)
        products.append({
            "product_id": pid,
            "product_name": name,
            "category_id": cat_id,
            "unit_cost": cost,
            "unit_price": round(cost * (1 + margin), 2),
            "weight_kg": round(random.uniform(0.05, 25.0), 2),
            "is_active": random.choices([True, False], weights=[90, 10])[0],
        })
        pid += 1
df_products = pd.DataFrame(products)

# ---------------------------------------------------------------------------
# 4. CUSTOMERS  (500 customers)
# ---------------------------------------------------------------------------
first_names = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael",
               "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
               "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen", "Daniel",
               "Lisa", "Matthew", "Nancy", "Anthony", "Betty", "Mark", "Margaret",
               "Donald", "Sandra", "Steven", "Ashley", "Andrew", "Dorothy", "Paul",
               "Kimberly", "Joshua", "Emily", "Kenneth", "Donna", "Kevin", "Michelle",
               "Brian", "Carol", "George", "Amanda", "Timothy", "Melissa", "Ronald", "Deborah"]

last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
              "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
              "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
              "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
              "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
              "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores"]

segments = ["Consumer", "Corporate", "Small Business", "Enterprise"]
cities_by_region = {
    1: ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"],
    2: ["Toronto", "Vancouver", "Montreal", "Calgary", "Ottawa"],
    3: ["London", "Manchester", "Birmingham", "Leeds", "Glasgow"],
    4: ["Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne"],
    5: ["Paris", "Lyon", "Marseille", "Toulouse", "Nice"],
    6: ["Tokyo", "Osaka", "Yokohama", "Nagoya", "Sapporo"],
    7: ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide"],
    8: ["Sao Paulo", "Rio de Janeiro", "Brasilia", "Salvador", "Fortaleza"],
    9: ["Mexico City", "Guadalajara", "Monterrey", "Puebla", "Tijuana"],
    10: ["Johannesburg", "Cape Town", "Durban", "Pretoria", "Port Elizabeth"],
}

customers = []
for cid in range(1, 501):
    region_id = random.choice(list(cities_by_region.keys()))
    signup = datetime(2020, 1, 1) + timedelta(days=random.randint(0, 2000))
    customers.append({
        "customer_id": cid,
        "first_name": random.choice(first_names),
        "last_name": random.choice(last_names),
        "email": f"customer{cid}@example.com",
        "segment": random.choices(segments, weights=[40, 30, 20, 10])[0],
        "city": random.choice(cities_by_region[region_id]),
        "region_id": region_id,
        "signup_date": signup.strftime("%Y-%m-%d"),
        "loyalty_points": random.randint(0, 15000),
        "is_active": random.choices([True, False], weights=[85, 15])[0],
    })
df_customers = pd.DataFrame(customers)

# ---------------------------------------------------------------------------
# 5. EMPLOYEES  (30 sales reps)
# ---------------------------------------------------------------------------
titles = ["Sales Rep", "Senior Sales Rep", "Account Manager", "Sales Manager", "Regional Director"]
employees = []
for eid in range(1, 31):
    hire = datetime(2018, 1, 1) + timedelta(days=random.randint(0, 2500))
    employees.append({
        "employee_id": eid,
        "employee_name": f"{random.choice(first_names)} {random.choice(last_names)}",
        "title": random.choices(titles, weights=[35, 25, 20, 15, 5])[0],
        "region_id": random.choice(df_regions["region_id"].tolist()),
        "hire_date": hire.strftime("%Y-%m-%d"),
        "salary": round(random.uniform(35000, 120000), 2),
        "commission_rate": round(random.uniform(0.02, 0.10), 3),
    })
df_employees = pd.DataFrame(employees)

# ---------------------------------------------------------------------------
# 6. ORDERS  (5000 orders over 3 years)
# ---------------------------------------------------------------------------
statuses = ["Completed", "Shipped", "Processing", "Cancelled", "Refunded"]
shipping_methods = ["Standard", "Express", "Overnight", "Economy", "Pickup"]

orders = []
for oid in range(1, 5001):
    order_date = datetime(2023, 1, 1) + timedelta(
        days=random.randint(0, 1095),  # ~3 years
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    status = random.choices(statuses, weights=[55, 20, 10, 10, 5])[0]
    orders.append({
        "order_id": oid,
        "customer_id": random.randint(1, 500),
        "employee_id": random.randint(1, 30),
        "order_date": order_date.strftime("%Y-%m-%d %H:%M"),
        "status": status,
        "shipping_method": random.choice(shipping_methods),
        "discount_pct": random.choices(
            [0, 5, 10, 15, 20, 25], weights=[40, 20, 15, 12, 8, 5]
        )[0],
    })
df_orders = pd.DataFrame(orders)

# ---------------------------------------------------------------------------
# 7. ORDER ITEMS  (avg ~2.5 items per order ≈ 12500 rows)
# ---------------------------------------------------------------------------
product_ids = df_products["product_id"].tolist()
order_items = []
for oid in range(1, 5001):
    n_items = random.choices([1, 2, 3, 4, 5], weights=[30, 30, 20, 12, 8])[0]
    chosen = random.sample(product_ids, n_items)
    for prod_id in chosen:
        qty = random.choices([1, 2, 3, 4, 5, 10], weights=[40, 25, 15, 10, 7, 3])[0]
        price = df_products.loc[df_products["product_id"] == prod_id, "unit_price"].values[0]
        order_items.append({
            "order_id": oid,
            "product_id": prod_id,
            "quantity": qty,
            "unit_price": price,
            "line_total": round(price * qty, 2),
        })
df_order_items = pd.DataFrame(order_items)

# ---------------------------------------------------------------------------
# 8. RETURNS  (~8% of order items)
# ---------------------------------------------------------------------------
return_reasons = [
    "Defective", "Wrong Item", "Not as Described", "Changed Mind",
    "Arrived Late", "Duplicate Order", "Better Price Found",
]
return_statuses = ["Approved", "Pending", "Denied"]
returns = []
rid = 1
for _, item in df_order_items.iterrows():
    if random.random() < 0.08:
        order_date_str = df_orders.loc[
            df_orders["order_id"] == item["order_id"], "order_date"
        ].values[0]
        order_dt = datetime.strptime(str(order_date_str), "%Y-%m-%d %H:%M")
        return_dt = order_dt + timedelta(days=random.randint(1, 45))
        returns.append({
            "return_id": rid,
            "order_id": item["order_id"],
            "product_id": item["product_id"],
            "return_date": return_dt.strftime("%Y-%m-%d"),
            "reason": random.choice(return_reasons),
            "refund_amount": round(item["line_total"] * random.uniform(0.5, 1.0), 2),
            "status": random.choices(return_statuses, weights=[60, 25, 15])[0],
        })
        rid += 1
df_returns = pd.DataFrame(returns)

# ---------------------------------------------------------------------------
# WRITE TO EXCEL (multi-sheet)
# ---------------------------------------------------------------------------
output_dir = Path(__file__).resolve().parent.parent / "data"
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / "sample_sales_data.xlsx"

with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
    df_regions.to_excel(writer, sheet_name="regions", index=False)
    df_categories.to_excel(writer, sheet_name="categories", index=False)
    df_products.to_excel(writer, sheet_name="products", index=False)
    df_customers.to_excel(writer, sheet_name="customers", index=False)
    df_employees.to_excel(writer, sheet_name="employees", index=False)
    df_orders.to_excel(writer, sheet_name="orders", index=False)
    df_order_items.to_excel(writer, sheet_name="order_items", index=False)
    df_returns.to_excel(writer, sheet_name="returns", index=False)

print(f"Generated: {output_path}")
print(f"  regions:      {len(df_regions):>6} rows")
print(f"  categories:   {len(df_categories):>6} rows")
print(f"  products:     {len(df_products):>6} rows")
print(f"  customers:    {len(df_customers):>6} rows")
print(f"  employees:    {len(df_employees):>6} rows")
print(f"  orders:       {len(df_orders):>6} rows")
print(f"  order_items:  {len(df_order_items):>6} rows")
print(f"  returns:      {len(df_returns):>6} rows")
print(f"  TOTAL:        {sum(len(df) for df in [df_regions, df_categories, df_products, df_customers, df_employees, df_orders, df_order_items, df_returns]):>6} rows")
