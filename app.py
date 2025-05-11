from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'

# MySQL Configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'passwd',
    'database': 'shop_db'
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            password VARCHAR(80) NOT NULL,
            is_admin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
    ''')
    
    # Create products table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            price FLOAT NOT NULL,
            stock INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
    ''')
    
    # Create orders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            product_id INT NOT NULL,
            quantity INT NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        ) ENGINE=InnoDB
    ''')
    
    # Check if admin user exists, if not create one
    cursor.execute('SELECT id FROM users WHERE username = %s', ('admin',))
    if not cursor.fetchone():
        cursor.execute('INSERT INTO users (username, password, is_admin) VALUES (%s, %s, %s)',
                      ('admin', 'admin123', True))
    
    # Add some sample products if none exist
    cursor.execute('SELECT COUNT(*) FROM products')
    if cursor.fetchone()[0] == 0:
        sample_products = [
            ('Laptop', 999.99, 10),
            ('Smartphone', 499.99, 15),
            ('Headphones', 99.99, 20),
            ('Tablet', 299.99, 8),
            ('Smartwatch', 199.99, 12)
        ]
        cursor.executemany('INSERT INTO products (name, price, stock) VALUES (%s, %s, %s)',
                          sample_products)
    
    conn.commit()
    cursor.close()
    conn.close()

# Initialize database when app starts
init_db()

# Admin check decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT is_admin FROM users WHERE id = %s', (session['user_id'],))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user or not user['is_admin']:
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def home():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM products')
    products = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('home.html', products=products)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if username exists
        cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return 'Username already exists'
        
        # Create new user
        cursor.execute('INSERT INTO users (username, password) VALUES (%s, %s)',
                      (username, password))
        conn.commit()
        cursor.close()
        conn.close()
        
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT id, is_admin, username 
            FROM users 
            WHERE username = %s 
            AND password = %s
        ''', (username, password))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            session['is_admin'] = user['is_admin']
            session['username'] = user['username']
            return redirect(url_for('home'))
        
        return 'Invalid username or password'
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    if 'cart' not in session:
        session['cart'] = {}
    
    cart = session['cart']
    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    session['cart'] = cart
    
    return redirect(url_for('cart'))

@app.route('/cart')
def cart():
    if 'cart' not in session:
        session['cart'] = {}
    
    cart_items = []
    total = 0
    
    if session['cart']:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        for product_id, quantity in session['cart'].items():
            cursor.execute('SELECT * FROM products WHERE id = %s', (product_id,))
            product = cursor.fetchone()
            if product:
                subtotal = product['price'] * quantity
                cart_items.append({
                    'product': product,
                    'quantity': quantity,
                    'subtotal': subtotal
                })
                total += subtotal
        
        cursor.close()
        conn.close()
    
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/checkout')
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'cart' not in session or not session['cart']:
        return redirect(url_for('cart'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create order for each item in cart
    for product_id, quantity in session['cart'].items():
        cursor.execute('''
            INSERT INTO orders (user_id, product_id, quantity)
            VALUES (%s, %s, %s)
        ''', (session['user_id'], product_id, quantity))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    session.pop('cart', None)
    return redirect(url_for('orders'))

@app.route('/orders')
def orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('''
        SELECT o.*, p.name as product_name
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.user_id = %s
        ORDER BY o.date DESC
    ''', (session['user_id'],))
    
    orders = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('orders.html', orders=orders)

# Admin routes
@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get counts
    cursor.execute('SELECT COUNT(*) as count FROM products')
    product_count = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM orders')
    order_count = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM users')
    user_count = cursor.fetchone()['count']
    
    cursor.close()
    conn.close()
    
    return render_template('admin/dashboard.html', 
                         product_count=product_count,
                         order_count=order_count,
                         user_count=user_count)

@app.route('/admin/products')
@admin_required
def admin_products():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM products')
    products = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin/products.html', products=products)

@app.route('/admin/products/add', methods=['GET', 'POST'])
@admin_required
def admin_add_product():
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('INSERT INTO products (name, price, stock) VALUES (%s, %s, %s)',
                      (name, price, stock))
        conn.commit()
        cursor.close()
        conn.close()
        
        return redirect(url_for('admin_products'))
    
    return render_template('admin/add_product.html')

@app.route('/admin/products/edit/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        
        cursor.execute('''
            UPDATE products 
            SET name = %s, price = %s, stock = %s 
            WHERE id = %s
        ''', (name, price, stock, product_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return redirect(url_for('admin_products'))
    
    cursor.execute('SELECT * FROM products WHERE id = %s', (product_id,))
    product = cursor.fetchone()
    cursor.close()
    conn.close()
    
    return render_template('admin/edit_product.html', product=product)

@app.route('/admin/products/delete/<int:product_id>')
@admin_required
def admin_delete_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE id = %s', (product_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('admin_products'))

@app.route('/admin/users')
@admin_required
def admin_users():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get all users with their order counts and last order date
    cursor.execute('''
        SELECT u.*, 
               COUNT(o.id) as order_count,
               MAX(o.date) as last_order_date
        FROM users u
        LEFT JOIN orders o ON u.id = o.user_id
        GROUP BY u.id
        ORDER BY u.id
    ''')
    
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/delete/<int:user_id>')
@admin_required
def admin_delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('admin_users'))

if __name__ == '__main__':
    app.run(debug=True)