from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify
from utils.db import SimpleDB
from utils.auth import SimpleAuth
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'ecommerce-secret-key-2024'

db = SimpleDB()
auth = SimpleAuth()

# Helper functions
def format_currency(amount):
    return f"{amount:,.0f} ₫"

app.jinja_env.filters['currency'] = format_currency

def get_cart_count():
    if 'user_id' not in session:
        return 0
    
    carts = db.load('carts.json')
    user_cart = next((c for c in carts if c['user_id'] == session['user_id'] and c['active']), None)
    
    if not user_cart:
        return 0
    
    cart_items = db.load('cart_items.json')
    user_items = [item for item in cart_items if item['cart_id'] == user_cart['id']]
    return sum(item['quantity'] for item in user_items)

def require_admin():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Bạn không có quyền truy cập trang này!', 'error')
        return redirect(url_for('home'))

def require_login():
    if 'user_id' not in session:
        flash('Vui lòng đăng nhập!', 'error')
        return redirect(url_for('login'))

# ==================== ROUTES ====================

@app.route('/')
def home():
    products = db.load('products.json')
    return render_template('index.html', products=products, cart_count=get_cart_count())

# ==================== AUTHENTICATION ====================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        
        users = db.load('users.json')
        
        if any(user['email'] == email for user in users):
            flash('Email đã tồn tại!', 'error')
            return render_template('register.html')
        
        new_user = {
            'id': db.get_next_id(users),
            'name': name,
            'email': email,
            'password_hash': auth.hash_password(password),
            'role': 'user'
        }
        users.append(new_user)
        db.save('users.json', users)
        
        flash('Đăng ký thành công! Hãy đăng nhập.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        users = db.load('users.json')
        user = next((u for u in users if u['email'] == email), None)
        
        if user and auth.verify_password(password, user['password_hash']):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['role'] = user['role']
            session['user_email'] = user['email']
            
            if user['role'] == 'admin':
                flash(f'Chào mừng admin {user["name"]}!', 'success')
            else:
                flash(f'Chào mừng {user["name"]}!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Email hoặc mật khẩu không đúng!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Đã đăng xuất!', 'info')
    return redirect(url_for('home'))

# ==================== PRODUCTS ====================

@app.route('/products')
def products():
    category_id = request.args.get('category', type=int)
    search = request.args.get('search', '')
    
    all_products = db.load('products.json')
    categories = db.load('categories.json')
    
    filtered_products = all_products
    
    if category_id:
        subcategory_ids = [cat['id'] for cat in categories if cat['parent_id'] == category_id]
        
        if subcategory_ids:
            filtered_products = [p for p in filtered_products if p['category_id'] in subcategory_ids]
        else:
            filtered_products = [p for p in filtered_products if p['category_id'] == category_id]
    
    if search:
        filtered_products = [p for p in filtered_products if search.lower() in p['name'].lower()]
    
    return render_template('products.html', 
                         products=filtered_products,
                         categories=categories,
                         selected_category=category_id,
                         search_query=search,
                         cart_count=get_cart_count())

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    products = db.load('products.json')
    product = next((p for p in products if p['id'] == product_id), None)
    
    if not product:
        flash('Sản phẩm không tồn tại!', 'error')
        return redirect(url_for('products'))
    
    return render_template('product_detail.html', product=product, cart_count=get_cart_count())

# ==================== CART & ORDERS (USER) ====================

@app.route('/cart')
def cart():
    require_login()
    
    carts = db.load('carts.json')
    user_cart = next((c for c in carts if c['user_id'] == session['user_id'] and c['active']), None)
    
    if not user_cart:
        return render_template('cart.html', cart_items=[], total=0, cart_count=0)
    
    cart_items = db.load('cart_items.json')
    user_items = [item for item in cart_items if item['cart_id'] == user_cart['id']]
    
    total = 0
    for item in user_items:
        product = next((p for p in db.load('products.json') if p['id'] == item['product_id']), None)
        if product:
            item['product'] = product
            item['subtotal'] = product['price'] * item['quantity']
            total += item['subtotal']
    
    return render_template('cart.html', cart_items=user_items, total=total, cart_count=get_cart_count())

@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    require_login()
    
    carts = db.load('carts.json')
    user_cart = next((c for c in carts if c['user_id'] == session['user_id'] and c['active']), None)
    
    if not user_cart:
        user_cart = {
            'id': db.get_next_id(carts),
            'user_id': session['user_id'],
            'active': True
        }
        carts.append(user_cart)
        db.save('carts.json', carts)
    
    cart_items = db.load('cart_items.json')
    existing_item = next((item for item in cart_items 
                         if item['cart_id'] == user_cart['id'] and item['product_id'] == product_id), None)
    
    if existing_item:
        existing_item['quantity'] += 1
    else:
        new_item = {
            'id': db.get_next_id(cart_items),
            'cart_id': user_cart['id'],
            'product_id': product_id,
            'quantity': 1
        }
        cart_items.append(new_item)
    
    db.save('cart_items.json', cart_items)
    flash('Đã thêm vào giỏ hàng!', 'success')
    return redirect(request.referrer or url_for('products'))

@app.route('/update_cart/<int:item_id>', methods=['POST'])
def update_cart(item_id):
    require_login()
    
    new_quantity = int(request.form['quantity'])
    
    if new_quantity <= 0:
        return remove_from_cart(item_id)
    
    cart_items = db.load('cart_items.json')
    item = next((item for item in cart_items if item['id'] == item_id), None)
    
    if item:
        item['quantity'] = new_quantity
        db.save('cart_items.json', cart_items)
        flash('Đã cập nhật giỏ hàng!', 'success')
    
    return redirect(url_for('cart'))

@app.route('/remove_from_cart/<int:item_id>')
def remove_from_cart(item_id):
    require_login()
    
    cart_items = db.load('cart_items.json')
    cart_items = [item for item in cart_items if item['id'] != item_id]
    db.save('cart_items.json', cart_items)
    flash('Đã xóa sản phẩm khỏi giỏ hàng!', 'success')
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    require_login()
    
    if request.method == 'POST':
        carts = db.load('carts.json')
        user_cart = next((c for c in carts if c['user_id'] == session['user_id'] and c['active']), None)
        
        if not user_cart:
            flash('Giỏ hàng trống!', 'error')
            return redirect(url_for('cart'))
        
        cart_items = db.load('cart_items.json')
        user_items = [item for item in cart_items if item['cart_id'] == user_cart['id']]
        
        if not user_items:
            flash('Giỏ hàng trống!', 'error')
            return redirect(url_for('cart'))
        
        total = 0
        products = db.load('products.json')
        
        for item in user_items:
            product = next((p for p in products if p['id'] == item['product_id']), None)
            if product:
                if product['stock'] < item['quantity']:
                    flash(f'Sản phẩm {product["name"]} không đủ số lượng!', 'error')
                    return redirect(url_for('cart'))
                total += product['price'] * item['quantity']
        
        orders = db.load('orders.json')
        new_order = {
            'id': db.get_next_id(orders),
            'user_id': session['user_id'],
            'total': total,
            'status': 'pending',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        orders.append(new_order)
        db.save('orders.json', orders)
        
        order_items = db.load('order_items.json')
        for item in user_items:
            product = next((p for p in products if p['id'] == item['product_id']), None)
            if product:
                new_order_item = {
                    'id': db.get_next_id(order_items),
                    'order_id': new_order['id'],
                    'product_id': item['product_id'],
                    'quantity': item['quantity'],
                    'price': product['price']
                }
                order_items.append(new_order_item)
                product['stock'] -= item['quantity']
        
        db.save('order_items.json', order_items)
        db.save('products.json', products)
        
        user_cart['active'] = False
        db.save('carts.json', carts)
        
        cart_items = [item for item in cart_items if item['cart_id'] != user_cart['id']]
        db.save('cart_items.json', cart_items)
        
        flash('Đặt hàng thành công! Cảm ơn bạn đã mua sắm.', 'success')
        return redirect(url_for('order_history'))
    
    carts = db.load('carts.json')
    user_cart = next((c for c in carts if c['user_id'] == session['user_id'] and c['active']), None)
    
    if not user_cart:
        flash('Giỏ hàng trống!', 'error')
        return redirect(url_for('cart'))
    
    cart_items = db.load('cart_items.json')
    user_items = [item for item in cart_items if item['cart_id'] == user_cart['id']]
    
    if not user_items:
        flash('Giỏ hàng trống!', 'error')
        return redirect(url_for('cart'))
    
    total = 0
    products = db.load('products.json')
    for item in user_items:
        product = next((p for p in products if p['id'] == item['product_id']), None)
        if product:
            total += product['price'] * item['quantity']
    
    return render_template('checkout.html', total=total, cart_count=get_cart_count())

@app.route('/orders')
def order_history():
    require_login()
    
    orders = db.load('orders.json')
    user_orders = [order for order in orders if order['user_id'] == session['user_id']]
    
    order_items = db.load('order_items.json')
    products = db.load('products.json')
    
    for order in user_orders:
        order['order_items'] = [item for item in order_items if item['order_id'] == order['id']]
        for item in order['order_items']:
            product = next((p for p in products if p['id'] == item['product_id']), None)
            if product:
                item['product_name'] = product['name']
    
    return render_template('orders.html', orders=user_orders, cart_count=get_cart_count())

# ==================== ADMIN ROUTES ====================

@app.route('/admin')
def admin_dashboard():
    require_admin()
    
    orders = db.load('orders.json')
    products = db.load('products.json')
    users = db.load('users.json')
    
    stats = {
        'total_orders': len(orders),
        'total_products': len(products),
        'total_users': len([u for u in users if u['role'] == 'user']),
        'total_revenue': sum(order['total'] for order in orders),
        'pending_orders': len([o for o in orders if o['status'] == 'pending'])
    }
    
    return render_template('admin/dashboard.html', stats=stats, cart_count=get_cart_count())

@app.route('/admin/products')
def admin_products():
    require_admin()
    
    products = db.load('products.json')
    categories = db.load('categories.json')
    
    return render_template('admin/products.html', products=products, categories=categories, cart_count=get_cart_count())

@app.route('/admin/products/add', methods=['GET', 'POST'])
def admin_add_product():
    require_admin()
    
    if request.method == 'POST':
        name = request.form['name']
        price = int(request.form['price'])
        stock = int(request.form['stock'])
        category_id = int(request.form['category_id'])
        description = request.form['description']
        image = request.form['image']
        
        products = db.load('products.json')
        
        new_product = {
            'id': db.get_next_id(products),
            'name': name,
            'price': price,
            'stock': stock,
            'category_id': category_id,
            'description': description,
            'image': image
        }
        
        products.append(new_product)
        db.save('products.json', products)
        
        flash('Thêm sản phẩm thành công!', 'success')
        return redirect(url_for('admin_products'))
    
    categories = db.load('categories.json')
    return render_template('admin/add_product.html', categories=categories, cart_count=get_cart_count())

@app.route('/admin/products/<int:product_id>/edit', methods=['GET', 'POST'])
def admin_edit_product(product_id):
    require_admin()
    
    products = db.load('products.json')
    product = next((p for p in products if p['id'] == product_id), None)
    
    if not product:
        flash('Sản phẩm không tồn tại!', 'error')
        return redirect(url_for('admin_products'))
    
    if request.method == 'POST':
        product['name'] = request.form['name']
        product['price'] = int(request.form['price'])
        product['stock'] = int(request.form['stock'])
        product['category_id'] = int(request.form['category_id'])
        product['description'] = request.form['description']
        product['image'] = request.form['image']
        
        db.save('products.json', products)
        flash('Cập nhật sản phẩm thành công!', 'success')
        return redirect(url_for('admin_products'))
    
    categories = db.load('categories.json')
    return render_template('admin/edit_product.html', product=product, categories=categories, cart_count=get_cart_count())

@app.route('/admin/products/<int:product_id>/delete', methods=['POST'])
def admin_delete_product(product_id):
    require_admin()
    
    products = db.load('products.json')
    products = [p for p in products if p['id'] != product_id]
    
    db.save('products.json', products)
    flash('Xóa sản phẩm thành công!', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/orders')
def admin_orders():
    require_admin()
    
    orders = db.load('orders.json')
    order_items = db.load('order_items.json')
    products = db.load('products.json')
    users = db.load('users.json')
    
    for order in orders:
        order['user_name'] = next((u['name'] for u in users if u['id'] == order['user_id']), 'Unknown')
        order['order_items'] = [item for item in order_items if item['order_id'] == order['id']]
        for item in order['order_items']:
            product = next((p for p in products if p['id'] == item['product_id']), None)
            if product:
                item['product_name'] = product['name']
    
    return render_template('admin/orders.html', orders=orders, cart_count=get_cart_count())

@app.route('/admin/orders/<int:order_id>/update', methods=['POST'])
def admin_update_order(order_id):
    require_admin()
    
    new_status = request.form['status']
    orders = db.load('orders.json')
    
    order = next((o for o in orders if o['id'] == order_id), None)
    if order:
        order['status'] = new_status
        db.save('orders.json', orders)
        flash('Cập nhật trạng thái đơn hàng thành công!', 'success')
    
    return redirect(url_for('admin_orders'))

@app.route('/admin/users')
def admin_users():
    require_admin()
    
    users = db.load('users.json')
    return render_template('admin/users.html', users=users, cart_count=get_cart_count())

if __name__ == '__main__':
    try:
        db.load('products.json')
        print("=" * 50)
        print("✅ ỨNG DỤNG ĐÃ SẴN SÀNG!")
        print("   Tài khoản demo:")
        print("   Admin: admin@example.com / admin123")
        print("   User:  user@example.com / user123")
        print("=" * 50)
        print("🌐 TRUY CẬP: http://localhost:5000")
        print("=" * 50)
    except Exception as e:
        print(f"Lỗi khi khởi tạo dữ liệu: {e}")
        try:
            from init_data import init_sample_data
            init_sample_data()
            print("✅ Đã khởi tạo dữ liệu mẫu")
        except Exception as e2:
            print(f"Lỗi khi chạy init_data: {e2}")
    
    app.run(debug=True, host='127.0.0.1', port=5000)