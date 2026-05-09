
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3, datetime, urllib.parse, unicodedata

app=Flask(__name__)
app.secret_key='dms_v8'
DB='dms_pro_v8.db'
PHONE='Sucursal Perico: 3884794349 | Sucursal El Carmen: 3885911211'

def db():
    c=sqlite3.connect(DB)
    c.row_factory=sqlite3.Row
    return c

def today(): return datetime.date.today().isoformat()
def now(): return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def money(v):
    try: return float(v or 0)
    except: return 0

def category_code(text):
    text=(text or 'GEN').strip().upper()
    text=''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c)!='Mn')
    letters=''.join(c for c in text if c.isalnum())
    return (letters or 'GEN')[:3].ljust(3,'X')

def next_inventory_code(cur, category, category_prefix=None):
    prefix=category_code(category_prefix or category)
    row=cur.execute("SELECT sku FROM inventory WHERE sku LIKE ? ORDER BY id DESC LIMIT 1",(prefix+'-%',)).fetchone()
    if not row or not row['sku']:
        n=1
    else:
        try: n=int(row['sku'].split('-')[-1])+1
        except: n=1
    return f"{prefix}-{n:03d}"

def init():
    con=db(); cur=con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT);
    CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY, name TEXT, phone TEXT, address TEXT);
    CREATE TABLE IF NOT EXISTS inventory_categories(id INTEGER PRIMARY KEY, name TEXT UNIQUE, code TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY, sku TEXT, category TEXT, item TEXT, detail TEXT, unit TEXT, cost_price REAL, retail_price REAL, wholesale_price REAL, stock_qty REAL, min_stock REAL, active TEXT);
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, code TEXT, document_type TEXT, order_module TEXT, reception_channel TEXT, client_id INTEGER, client_name TEXT, client_phone TEXT, client_address TEXT, date_taken TEXT, date_delivery TEXT, status TEXT, receptionist TEXT, client_notes TEXT, school_name TEXT, school_grade TEXT, fabric_type TEXT, team_design_notes TEXT, discount REAL, subtotal REAL, total REAL, deposit REAL, balance REAL, payment_method TEXT, payment_note TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS general_items(id INTEGER PRIMARY KEY, order_id INTEGER, inventory_id INTEGER, product TEXT, detail TEXT, qty REAL, unit_price REAL, subtotal REAL);
    CREATE TABLE IF NOT EXISTS apparel_items(id INTEGER PRIMARY KEY, order_id INTEGER, article TEXT, person_name TEXT, upper_size TEXT, lower_size TEXT, price REAL);
    CREATE TABLE IF NOT EXISTS apparel_sponsors(id INTEGER PRIMARY KEY, order_id INTEGER, garment_part TEXT, location TEXT, sponsor_name TEXT, note TEXT);
    CREATE TABLE IF NOT EXISTS grad_items(id INTEGER PRIMARY KEY, order_id INTEGER, person_name TEXT, cap_size TEXT, stole_size TEXT, note TEXT, price REAL);
    CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY, order_id INTEGER, dt TEXT, concept TEXT, amount REAL, method TEXT, note TEXT, user TEXT);
    CREATE TABLE IF NOT EXISTS cash(id INTEGER PRIMARY KEY, date TEXT, dt TEXT, type TEXT, concept TEXT, amount REAL, method TEXT, order_id INTEGER, user TEXT, note TEXT);
    CREATE TABLE IF NOT EXISTS cash_sessions(id INTEGER PRIMARY KEY, date TEXT, opened_at TEXT, closed_at TEXT, opening_cash REAL, closing_cash REAL, total_efectivo REAL, total_transferencia REAL, total_gastos REAL, final_cash REAL, user TEXT, notes TEXT, status TEXT);
    """)
    if cur.execute('SELECT COUNT(*) c FROM users').fetchone()['c']==0:
        cur.execute("INSERT INTO users(username,password,role) VALUES('admin','admin','Administrador')")
    if cur.execute('SELECT COUNT(*) c FROM inventory_categories').fetchone()['c']==0:
        cats=[('Indumentaria','IND'),('Polímero','POL'),('Remeras','REM'),('Vidrios','VID'),('Escolar','ESC')]
        cur.executemany('INSERT INTO inventory_categories(name,code) VALUES(?,?)', cats)
    if cur.execute('SELECT COUNT(*) c FROM inventory').fetchone()['c']==0:
        rows=[('INS-001','Insumos','Taza blanca AAA','Para sublimar','u',2200,3500,3000,5,10,'Sí'),
              ('INS-002','Insumos','Vinilo textil blanco','Metro','m',1200,2200,1900,3,10,'Sí'),
              ('IND-001','Indumentaria','Remera Dry Fit Sublimada','Frente completo','u',4200,6500,5900,12,15,'Sí'),
              ('IND-002','Indumentaria','Short deportivo','Con logo','u',2500,4000,3500,8,15,'Sí'),
              ('EGR-001','Egresados','Birrete personalizado','Color a elección','u',5000,8500,7500,10,15,'Sí'),
              ('EGR-002','Egresados','Estola personalizada','Con nombre/logo','u',4500,7500,6500,10,15,'Sí')]
        cur.executemany('INSERT INTO inventory(sku,category,item,detail,unit,cost_price,retail_price,wholesale_price,stock_qty,min_stock,active) VALUES(?,?,?,?,?,?,?,?,?,?,?)',rows)
    con.commit(); con.close()

def login_required(fn):
    def wrap(*a,**k):
        if 'user' not in session: return redirect('/login')
        return fn(*a,**k)
    wrap.__name__=fn.__name__
    return wrap

def prefix(doc): return 'FAC' if doc=='Pedido/Factura' else 'PRE'

def next_code(doc,module):
    con=db()
    n=con.execute('SELECT COUNT(*) c FROM orders WHERE document_type=? AND order_module=?',(doc,module)).fetchone()['c']+1
    con.close()
    mod={'General':'GEN','Indumentaria':'IND','Birretes/Estolas':'EGR'}[module]
    return f'{prefix(doc)}-{mod}-{n:06d}'

def save_client(cur,name,phone,address):
    name=(name or '').strip(); phone=(phone or '').strip(); address=(address or '').strip()
    if not name: return None
    old=cur.execute('SELECT * FROM clients WHERE name=? AND phone=?',(name,phone)).fetchone()
    if old:
        cur.execute('UPDATE clients SET address=? WHERE id=?',(address,old['id']))
        return old['id']
    cur.execute('INSERT INTO clients(name,phone,address) VALUES(?,?,?)',(name,phone,address))
    return cur.lastrowid

def register_cash_payment(cur, oid, code, concept, amount, method, note):
    cur.execute('INSERT INTO payments(order_id,dt,concept,amount,method,note,user) VALUES(?,?,?,?,?,?,?)',(oid,now(),concept,amount,method,note,session.get('user','admin')))
    cur.execute('INSERT INTO cash(date,dt,type,concept,amount,method,order_id,user,note) VALUES(?,?,?,?,?,?,?,?,?)',(today(),now(),'Ingreso',f'{concept} {code}',amount,method,oid,session.get('user','admin'),note))

def common_order_insert(cur, doc, module, subtotal, extra):
    code=next_code(doc,module)
    cid=save_client(cur, request.form.get('client_name'), request.form.get('client_phone'), request.form.get('client_address'))
    discount=money(request.form.get('discount')); total=max(0,subtotal-discount)
    deposit=0 if doc=='Presupuesto' else money(request.form.get('deposit'))
    balance=max(0,total-deposit)
    vals=(code,doc,module,request.form.get('reception_channel'),cid,request.form.get('client_name'),request.form.get('client_phone'),request.form.get('client_address'),request.form.get('date_taken') or today(),request.form.get('date_delivery'),request.form.get('status'),request.form.get('receptionist'),request.form.get('client_notes'),extra.get('school_name'),extra.get('school_grade'),extra.get('fabric_type'),extra.get('team_design_notes'),discount,subtotal,total,deposit,balance,request.form.get('payment_method'),request.form.get('payment_note'),now())
    cur.execute('''INSERT INTO orders(code,document_type,order_module,reception_channel,client_id,client_name,client_phone,client_address,date_taken,date_delivery,status,receptionist,client_notes,school_name,school_grade,fabric_type,team_design_notes,discount,subtotal,total,deposit,balance,payment_method,payment_note,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', vals)
    oid=cur.lastrowid
    if deposit>0:
        register_cash_payment(cur,oid,code,'Seña',deposit,request.form.get('payment_method'),request.form.get('payment_note'))
    return oid,code

def whatsapp_url(order, msg=None):
    phone=(order['client_phone'] or '').replace(' ','').replace('-','')
    if not phone: return ''
    text=msg or f"Hola, desde DMS Sublimaciones te informamos que tu pedido {order['code']} está en estado: {order['status']}. Saldo pendiente: ${order['balance']:.2f}."
    return 'https://wa.me/54'+phone+'?text='+urllib.parse.quote(text)


def day_totals(cur, date):
    efectivo = cur.execute("SELECT COALESCE(SUM(amount),0) s FROM cash WHERE date=? AND method='Efectivo' AND type!='Gasto'", (date,)).fetchone()['s']
    transferencia = cur.execute("SELECT COALESCE(SUM(amount),0) s FROM cash WHERE date=? AND method='Transferencia' AND type!='Gasto'", (date,)).fetchone()['s']
    gastos_ef = cur.execute("SELECT COALESCE(SUM(amount),0) s FROM cash WHERE date=? AND method='Efectivo' AND type='Gasto'", (date,)).fetchone()['s']
    gastos_tr = cur.execute("SELECT COALESCE(SUM(amount),0) s FROM cash WHERE date=? AND method='Transferencia' AND type='Gasto'", (date,)).fetchone()['s']
    return efectivo, transferencia, gastos_ef, gastos_tr

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        con=db(); u=con.execute('SELECT * FROM users WHERE username=? AND password=?',(request.form['username'],request.form['password'])).fetchone(); con.close()
        if u:
            session['user']=u['username']; session['role']=u['role']
            return redirect('/')
        flash('Usuario o contraseña incorrectos')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); return redirect('/login')

@app.route('/')
@login_required
def dashboard():
    con=db(); cur=con.cursor()
    ef,tr,gef,gtr=day_totals(cur,today())
    ingresos=ef+tr; gastos=gef+gtr
    orders=cur.execute('SELECT * FROM orders ORDER BY id DESC LIMIT 8').fetchall()
    open_cash=cur.execute("SELECT * FROM cash_sessions WHERE date=? AND status='Abierta' ORDER BY id DESC LIMIT 1",(today(),)).fetchone()
    con.close()
    return render_template('dashboard.html',ingresos=ingresos,gastos=gastos,efectivo=ef,transferencia=tr,gastos_ef=gef,gastos_tr=gtr,orders=orders,open_cash=open_cash)


def get_category_prefix(cur, category_name, manual_code=None):
    if manual_code:
        return category_code(manual_code)
    row=cur.execute('SELECT code FROM inventory_categories WHERE name=?',(category_name,)).fetchone()
    if row and row['code']:
        return row['code']
    return category_code(category_name)

@app.route('/inventory',methods=['GET','POST'])
@login_required
def inventory():
    con=db(); cur=con.cursor()
    if request.method=='POST':
        category=request.form.get('category')
        sku=next_inventory_code(cur, category, get_category_prefix(cur, category, request.form.get('category_prefix')))
        cur.execute('INSERT INTO inventory(sku,category,item,detail,unit,cost_price,retail_price,wholesale_price,stock_qty,min_stock,active) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (sku,category,request.form['item'],request.form.get('detail'),'u',0,money(request.form.get('retail_price')),money(request.form.get('wholesale_price')),money(request.form.get('stock_qty')),money(request.form.get('min_stock')),'Sí'))
        con.commit(); return redirect('/inventory')
    q=(request.args.get('q') or '').strip()
    if q:
        rows=cur.execute("SELECT * FROM inventory WHERE active!='No' AND (sku LIKE ? OR item LIKE ? OR category LIKE ?) ORDER BY category,item",(f'%{q}%',f'%{q}%',f'%{q}%')).fetchall()
    else:
        rows=cur.execute("SELECT * FROM inventory WHERE active!='No' ORDER BY category,item").fetchall()
    categories=cur.execute('SELECT * FROM inventory_categories ORDER BY name').fetchall()
    grouped={}
    for r in rows:
        grouped.setdefault(r['category'],[]).append(r)
    con.close()
    return render_template('inventory.html',rows=rows,grouped=grouped,categories=categories,q=q)



@app.route('/inventory/category/add',methods=['POST'])
@login_required
def inventory_category_add():
    con=db(); cur=con.cursor()
    name=(request.form.get('name') or '').strip()
    code=category_code(request.form.get('code') or name)
    if name:
        try:
            cur.execute('INSERT INTO inventory_categories(name,code) VALUES(?,?)',(name,code))
            con.commit()
        except Exception:
            pass
    con.close()
    return redirect('/inventory')

@app.route('/inventory/<int:iid>/delete',methods=['POST'])
@login_required
def inventory_delete(iid):
    con=db(); cur=con.cursor()
    cur.execute("UPDATE inventory SET active='No' WHERE id=?",(iid,))
    con.commit(); con.close()
    return redirect('/inventory')

@app.route('/inventory/<int:iid>/edit',methods=['GET','POST'])
@login_required
def inventory_edit(iid):
    con=db(); cur=con.cursor()
    item=cur.execute('SELECT * FROM inventory WHERE id=?',(iid,)).fetchone()
    if request.method=='POST':
        cur.execute('UPDATE inventory SET category=?, item=?, detail=?, retail_price=?, wholesale_price=?, stock_qty=?, min_stock=? WHERE id=?',
                    (request.form.get('category'),request.form.get('item'),request.form.get('detail'),money(request.form.get('retail_price')),money(request.form.get('wholesale_price')),money(request.form.get('stock_qty')),money(request.form.get('min_stock')),iid))
        con.commit(); con.close(); return redirect('/inventory')
    con.close(); return render_template('inventory_edit.html',item=item)

@app.route('/api/inventory/<int:iid>')
@login_required
def api_inventory(iid):
    con=db(); r=con.execute('SELECT * FROM inventory WHERE id=?',(iid,)).fetchone(); con.close()
    return jsonify(dict(r) if r else {})

@app.route('/orders')
@login_required
def orders():
    q=(request.args.get('q') or '').strip()
    con=db()
    if q:
        rows=con.execute("SELECT * FROM orders WHERE code LIKE ? OR client_name LIKE ? ORDER BY id DESC",(f'%{q}%',f'%{q}%')).fetchall()
    else:
        rows=con.execute('SELECT * FROM orders ORDER BY id DESC').fetchall()
    con.close()
    return render_template('orders.html',rows=rows,filter_name='Todos los pedidos',q=q)

@app.route('/orders/new/general',methods=['GET','POST'])
@login_required
def new_general():
    con=db(); cur=con.cursor(); inv=cur.execute("SELECT * FROM inventory WHERE active='Sí' ORDER BY category,item").fetchall()
    if request.method=='POST':
        doc=request.form.get('document_type'); subtotal=0; rows=[]
        for i in range(1,16):
            inv_id=request.form.get(f'inv_id_{i}') or None
            product=request.form.get(f'product_{i}') or ''
            detail=request.form.get(f'detail_{i}') or ''
            qty=money(request.form.get(f'qty_{i}'))
            price=money(request.form.get(f'price_{i}'))
            if product and qty>0:
                st=qty*price; subtotal+=st; rows.append((inv_id,product,detail,qty,price,st))
        oid,code=common_order_insert(cur,doc,'General',subtotal,{})
        for row in rows:
            cur.execute('INSERT INTO general_items(order_id,inventory_id,product,detail,qty,unit_price,subtotal) VALUES(?,?,?,?,?,?,?)',(oid,*row))
        con.commit(); con.close()
        return redirect(f'/orders/{oid}')
    con.close()
    return render_template('new_general.html',inv=inv,today=today())

@app.route('/orders/new/indumentaria',methods=['GET','POST'])
@login_required
def new_indumentaria():
    articles=['Remera sola','Musculosa mujer','Musculosa hombre','Conjunto invierno','Conjunto verano','Chomba pique','Chomba algodon','Buzo full print','Buzo algodon','Campera algodon','Campera full print']
    sizes=['','4','6','8','10','12','14','16','S','M','L','XL','XXL','XXXL']
    upper=['Manga derecha','Manga izquierda','Espalda superior','Espalda inferior','Espalda central','Frente izquierdo','Frente derecho','Frente central','Frente inferior','Hombro derecho','Hombro izquierdo']
    lower=['Frente derecho','Frente izquierdo','Espalda derecho','Espalda izquierdo']
    if request.method=='POST':
        con=db(); cur=con.cursor(); doc=request.form.get('document_type')
        subtotal=0; item_rows=[]
        for i in range(1,int(request.form.get('item_count','1'))+1):
            article=request.form.get(f'article_{i}') or ''; name=request.form.get(f'name_{i}') or ''; upper_size=request.form.get(f'upper_{i}') or ''; lower_size=request.form.get(f'lower_{i}') or ''; price=money(request.form.get(f'price_{i}'))
            if article or name or upper_size or lower_size or price>0:
                subtotal+=price; item_rows.append((article,name,upper_size,lower_size,price))
        oid,code=common_order_insert(cur,doc,'Indumentaria',subtotal,{'fabric_type':request.form.get('fabric_type'),'team_design_notes':request.form.get('team_design_notes')})
        for row in item_rows: cur.execute('INSERT INTO apparel_items(order_id,article,person_name,upper_size,lower_size,price) VALUES(?,?,?,?,?,?)',(oid,*row))
        for i in range(1,int(request.form.get('sponsor_count','1'))+1):
            gp=request.form.get(f'sponsor_part_{i}') or ''; loc=request.form.get(f'sponsor_location_{i}') or ''; sp=request.form.get(f'sponsor_name_{i}') or ''; note=request.form.get(f'sponsor_note_{i}') or ''
            if loc or sp: cur.execute('INSERT INTO apparel_sponsors(order_id,garment_part,location,sponsor_name,note) VALUES(?,?,?,?,?)',(oid,gp,loc,sp,note))
        con.commit(); con.close(); return redirect(f'/orders/{oid}')
    return render_template('new_indumentaria.html',today=today(),articles=articles,sizes=sizes,upper_locations=upper,lower_locations=lower)

@app.route('/orders/new/egresados',methods=['GET','POST'])
@login_required
def new_egresados():
    cap_sizes=['','50cm','52cm','54cm','56cm','58cm','60cm','62cm','64cm']
    stole_sizes=['','65cm','75cm','85cm','95cm']
    if request.method=='POST':
        con=db(); cur=con.cursor(); doc=request.form.get('document_type')
        subtotal=0; rows=[]
        count=int(request.form.get('item_count','1'))
        for i in range(1,count+1):
            name=request.form.get(f'name_{i}') or ''; cap=request.form.get(f'cap_{i}') or ''; stole=request.form.get(f'stole_{i}') or ''; note=request.form.get(f'note_{i}') or ''; price=money(request.form.get(f'price_{i}'))
            if name or cap or stole or note or price>0:
                subtotal+=price; rows.append((name,cap,stole,note,price))
        oid,code=common_order_insert(cur,doc,'Birretes/Estolas',subtotal,{'school_name':request.form.get('school_name'), 'school_grade':request.form.get('school_grade')})
        for row in rows: cur.execute('INSERT INTO grad_items(order_id,person_name,cap_size,stole_size,note,price) VALUES(?,?,?,?,?,?)',(oid,*row))
        con.commit(); con.close(); return redirect(f'/orders/{oid}')
    return render_template('new_egresados.html',today=today(),cap_sizes=cap_sizes,stole_sizes=stole_sizes)

@app.route('/orders/<int:oid>')
@login_required
def view_order(oid):
    con=db()
    order=con.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    general=con.execute('SELECT * FROM general_items WHERE order_id=?',(oid,)).fetchall()
    apparel=con.execute('SELECT * FROM apparel_items WHERE order_id=?',(oid,)).fetchall()
    sponsors=con.execute('SELECT * FROM apparel_sponsors WHERE order_id=?',(oid,)).fetchall()
    grads=con.execute('SELECT * FROM grad_items WHERE order_id=?',(oid,)).fetchall()
    con.close()
    return render_template('order_view.html',order=order,general=general,apparel=apparel,sponsors=sponsors,grads=grads,wa=whatsapp_url(order),business_phone=PHONE)

@app.route('/orders/<int:oid>/edit',methods=['GET','POST'])
@login_required
def edit_order(oid):
    con=db(); cur=con.cursor()
    order=cur.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    if request.method=='POST':
        discount=money(request.form.get('discount')); total=max(0,money(request.form.get('subtotal'))-discount); deposit=money(request.form.get('deposit')); balance=max(0,total-deposit)
        cur.execute('''UPDATE orders SET client_name=?, client_phone=?, client_address=?, date_delivery=?, status=?, receptionist=?, client_notes=?, school_name=?, school_grade=?, fabric_type=?, team_design_notes=?, discount=?, subtotal=?, total=?, deposit=?, balance=?, payment_method=?, payment_note=? WHERE id=?''',
                    (request.form.get('client_name'),request.form.get('client_phone'),request.form.get('client_address'),request.form.get('date_delivery'),request.form.get('status'),request.form.get('receptionist'),request.form.get('client_notes'),request.form.get('school_name'),request.form.get('school_grade'),request.form.get('fabric_type'),request.form.get('team_design_notes'),discount,money(request.form.get('subtotal')),total,deposit,balance,request.form.get('payment_method'),request.form.get('payment_note'),oid))
        con.commit(); con.close()
        return redirect(f'/orders/{oid}')
    con.close()
    return render_template('edit_order.html',order=order)

@app.route('/orders/<int:oid>/status',methods=['POST'])
@login_required
def update_status(oid):
    status=request.form.get('status')
    con=db(); cur=con.cursor()
    cur.execute('UPDATE orders SET status=? WHERE id=?',(status,oid)); con.commit()
    order=cur.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone(); con.close()
    url=whatsapp_url(order, f"Hola, desde DMS Sublimaciones te informamos que tu pedido {order['code']} cambió de estado a: {status}.")
    return redirect(url or '/orders')

@app.route('/orders/<int:oid>/workshop')
@login_required
def workshop(oid):
    con=db()
    order=con.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    apparel=con.execute('SELECT * FROM apparel_items WHERE order_id=?',(oid,)).fetchall()
    sponsors=con.execute('SELECT * FROM apparel_sponsors WHERE order_id=?',(oid,)).fetchall()
    grads=con.execute('SELECT * FROM grad_items WHERE order_id=?',(oid,)).fetchall()
    con.close()
    if order['order_module']=='Indumentaria': return render_template('workshop_indumentaria.html',order=order,apparel=apparel,sponsors=sponsors)
    if order['order_module']=='Birretes/Estolas': return render_template('workshop_egresados.html',order=order,grads=grads)
    return redirect(f'/orders/{oid}')

@app.route('/clients')
@login_required
def clients():
    q=(request.args.get('q') or '').strip()
    con=db()
    if q: rows=con.execute('SELECT * FROM clients WHERE name LIKE ? OR phone LIKE ? ORDER BY name',(f'%{q}%',f'%{q}%')).fetchall()
    else: rows=con.execute('SELECT * FROM clients ORDER BY name').fetchall()
    con.close()
    return render_template('clients.html',rows=rows,q=q)

@app.route('/clients/<int:cid>')
@login_required
def client_history(cid):
    con=db(); client=con.execute('SELECT * FROM clients WHERE id=?',(cid,)).fetchone(); rows=con.execute('SELECT * FROM orders WHERE client_id=? ORDER BY id DESC',(cid,)).fetchall(); con.close()
    return render_template('client_history.html',client=client,rows=rows)

@app.route('/cash',methods=['GET','POST'])
@login_required
def cash():
    con=db(); cur=con.cursor()
    if request.method=='POST':
        cur.execute('INSERT INTO cash(date,dt,type,concept,amount,method,user,note) VALUES(?,?,?,?,?,?,?,?)',(today(),now(),request.form.get('type'),request.form.get('concept'),money(request.form.get('amount')),request.form.get('method'),session['user'],request.form.get('note')))
        con.commit(); return redirect('/cash')
    q=(request.args.get('q') or '').strip()
    found=[]
    if q: found=cur.execute("SELECT * FROM orders WHERE (code LIKE ? OR client_name LIKE ?) AND balance>0 ORDER BY id DESC",(f'%{q}%',f'%{q}%')).fetchall()
    moves=cur.execute('SELECT * FROM cash ORDER BY id DESC LIMIT 50').fetchall()
    ef,tr,gef,gtr=day_totals(cur,today())
    open_cash=cur.execute("SELECT * FROM cash_sessions WHERE date=? AND status='Abierta' ORDER BY id DESC LIMIT 1",(today(),)).fetchone()
    con.close()
    return render_template('cash.html',moves=moves,efectivo=ef,transferencia=tr,gastos=gef+gtr,gastos_ef=gef,gastos_tr=gtr,saldo_efectivo=ef-gef,q=q,found=found,open_cash=open_cash)

@app.route('/cash/charge/<int:oid>',methods=['POST'])
@login_required
def cash_charge(oid):
    con=db(); cur=con.cursor()
    order=cur.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    amount=money(request.form.get('amount')) or money(order['balance'])
    method=request.form.get('method') or 'Efectivo'
    note=request.form.get('note') or 'Cobro de saldo'
    new_deposit=money(order['deposit'])+amount
    new_balance=max(0,money(order['total'])-new_deposit)
    cur.execute('UPDATE orders SET deposit=?, balance=?, payment_method=? WHERE id=?',(new_deposit,new_balance,method,oid))
    register_cash_payment(cur,oid,order['code'],'Cobro saldo',amount,method,note)
    con.commit(); con.close()
    return redirect('/cash')


@app.route('/finance')
@login_required
def finance():
    month=request.args.get('month') or today()[:7]
    con=db(); cur=con.cursor()
    rows=cur.execute("""SELECT date, SUM(CASE WHEN type!='Gasto' THEN amount ELSE 0 END) ingresos, SUM(CASE WHEN type='Gasto' THEN amount ELSE 0 END) gastos FROM cash WHERE substr(date,1,7)=? GROUP BY date ORDER BY date""",(month,)).fetchall()
    mod_rows=cur.execute('SELECT order_module, COUNT(*) c FROM orders WHERE substr(date_taken,1,7)=? GROUP BY order_module',(month,)).fetchall()
    ingresos=sum([r['ingresos'] or 0 for r in rows]); gastos=sum([r['gastos'] or 0 for r in rows])
    con.close(); return render_template('finance.html',month=month,rows=rows,mod_rows=mod_rows,ingresos=ingresos,gastos=gastos)

@app.route('/finance/day/<date>')
@login_required
def finance_day(date):
    con=db(); cur=con.cursor()
    moves=cur.execute('SELECT * FROM cash WHERE date=? ORDER BY dt',(date,)).fetchall()
    orders=cur.execute('SELECT * FROM orders WHERE date_taken=? OR substr(created_at,1,10)=? ORDER BY id DESC',(date,date)).fetchall()
    session_row=cur.execute('SELECT * FROM cash_sessions WHERE date=? ORDER BY id DESC LIMIT 1',(date,)).fetchone()
    ef,tr,gef,gtr=day_totals(cur,date); con.close()
    return render_template('finance_day.html',date=date,moves=moves,orders=orders,session_row=session_row,ef=ef,tr=tr,gef=gef,gtr=gtr)

@app.route('/cash/open',methods=['POST'])
@login_required
def cash_open():
    con=db(); cur=con.cursor()
    exists=cur.execute("SELECT * FROM cash_sessions WHERE date=? AND status='Abierta'",(today(),)).fetchone()
    if not exists:
        cur.execute('INSERT INTO cash_sessions(date,opened_at,opening_cash,user,notes,status) VALUES(?,?,?,?,?,?)',(today(),now(),money(request.form.get('opening_cash')),session['user'],request.form.get('notes'),'Abierta'))
        con.commit()
    con.close(); return redirect('/cash')

@app.route('/cash/close',methods=['POST'])
@login_required
def cash_close():
    con=db(); cur=con.cursor()
    ses=cur.execute("SELECT * FROM cash_sessions WHERE date=? AND status='Abierta' ORDER BY id DESC LIMIT 1",(today(),)).fetchone()
    ef,tr,gef,gtr=day_totals(cur,today())
    if ses:
        final_cash=money(ses['opening_cash'])+ef-gef
        cur.execute("UPDATE cash_sessions SET closed_at=?, closing_cash=?, total_efectivo=?, total_transferencia=?, total_gastos=?, final_cash=?, notes=?, status='Cerrada' WHERE id=?",(now(),money(request.form.get('closing_cash')),ef,tr,gef+gtr,final_cash,request.form.get('notes'),ses['id']))
        con.commit()
    con.close(); return redirect('/cash')
init()
if __name__=='__main__':
    app.run(host='0.0.0.0',port=5000)
