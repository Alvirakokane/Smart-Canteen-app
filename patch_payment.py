"""Run ONCE from the SmartCanteen folder (next to app.py):   python patch_payment.py
Changes only the payment part of static/index.html: Cash or PhonePe. Design stays the same.
A backup is saved as static/index.backup.html."""
import re, shutil, sys

P = "static/index.html"
h = open(P, encoding="utf-8").read()
if "phonepe://" in h:
    sys.exit("Already patched.")
shutil.copy(P, "static/index.backup.html")

def swap(old, new):
    global h
    if h.count(old) != 1:
        sys.exit("Could not find this part in index.html, nothing was changed:\n  " + old[:80])
    h = h.replace(old, new)

NEWPAY = r'''/* payment */
const stag=x=>{const s=x.status,l={paid:x.method==='cash'?'Paid · Cash':'Paid · PhonePe',unpaid:'Pay at counter',pending:'Awaiting payment',cancelled:'Cancelled'}[s]||s;return `<span class="tag ${s==='paid'?'':'am'}">${esc(l)}</span>`};
function openPay(id){
 const i=MENU.find(x=>x.id==id);if(!i)return;let q=1,meth='cash';
 const o=document.createElement('div');o.className='ov';document.body.appendChild(o);const close=()=>o.remove();o.onclick=e=>{if(e.target===o)close()};
 const done=r=>{o.innerHTML=`<div class="sheet" style="text-align:center"><svg width="90" height="90" viewBox="0 0 90 90"><circle class="draw" pathLength="1" cx="45" cy="45" r="40" fill="none" stroke="#0e5a52" stroke-width="5"/><path class="draw" pathLength="1" d="M27 46l12 12 24-26" fill="none" stroke="#0e5a52" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/></svg>
  <h2>Order placed</h2><p class="sub">Token <b style="color:var(--teal);font-size:1.5rem">#${r.id}</b><br>${meth==='phonepe'?`Paid ${rupee(r.total)} via PhonePe · ${esc(r.txn)}`:`Pay ${rupee(r.total)} in cash at the counter`}</p><button class="btn full" id="dn2">View my orders</button></div>`;
  play();$('#dn2').onclick=()=>{close();go('orders')}};
 const wait=r=>{const p=r.pay,qs=`pa=${encodeURIComponent(p.vpa)}&pn=${encodeURIComponent(p.name)}&am=${r.total}&cu=INR&tn=${encodeURIComponent(p.note)}&tr=SC${r.id}`,link='phonepe://pay?'+qs;
  o.innerHTML=`<div class="sheet" style="text-align:center"><h3>Pay ${rupee(r.total)} in PhonePe</h3><p class="sub">PhonePe opens on your phone. After paying, come back here and enter the 12-digit UTR (reference number) shown in PhonePe.</p><a class="btn full" style="display:block;text-decoration:none" href="${esc(link)}">Open PhonePe</a><div id="uq" style="display:grid;place-items:center;margin:14px 0 4px"></div><p class="sub" style="margin:0 0 6px;font-size:.8rem">On a computer, scan this QR with PhonePe.</p><label for="utr" style="text-align:left">UTR / reference number</label><input id="utr" inputmode="numeric" maxlength="12" placeholder="12 digits"><div class="err" id="pe" role="alert"></div><button class="btn full" id="ok">I have paid</button><button class="btn ghost full" id="cn" style="margin-top:8px">Cancel order</button></div>`;
  if(window.QRCode)new QRCode($('#uq'),{text:'upi://pay?'+qs,width:130,height:130,colorDark:'#0e5a52'});
  if(/Android|iPhone|iPad/i.test(navigator.userAgent))setTimeout(()=>{location.href=link},300);
  $('#ok').onclick=async()=>{try{done(await api('/orders/'+r.id+'/confirm',{method:'POST',body:{utr:$('#utr').value}}))}catch(x){$('#pe').textContent=x.message}};
  $('#cn').onclick=async()=>{try{await api('/orders/'+r.id+'/cancel',{method:'POST'})}catch{}close();toast('Order cancelled')}};
 const draw=()=>{const lbl=meth==='cash'?'Place order':'Pay '+rupee(i.price*q)+' with PhonePe';
  o.innerHTML=`<div class="sheet" role="dialog" aria-label="Payment"><div class="nhead"><div class="dish" style="width:56px;height:56px;animation:none;margin:0">${pic(i)}</div><div><h3>${esc(i.name)}</h3><span class="sub" style="margin:0">${rupee(i.price)} each</span></div></div>
  <div class="row"><span>Quantity</span><span class="qty"><button id="qm" aria-label="Fewer">−</button><b>${q}</b><button id="qp" aria-label="More">+</button></span></div>
  <div class="row"><span>Total</span><b style="font-size:1.3rem;color:var(--teal)">${rupee(i.price*q)}</b></div>
  <p class="sub" style="margin:14px 0 0">Payment method</p>
  <button class="opt ${meth==='cash'?'on':''}" data-m="cash"><span style="font-size:1.6rem">💵</span><span><b>Cash</b><br><small>Pay at the counter when you collect</small></span></button>
  <button class="opt ${meth==='phonepe'?'on':''}" data-m="phonepe"><span style="font-size:1.6rem">📱</span><span><b>PhonePe</b><br><small>PhonePe opens so you can pay now</small></span></button>
  <div class="err" id="pe" role="alert"></div><button class="btn full" id="go">${lbl}</button><button class="btn ghost full" id="cl" style="margin-top:8px">Cancel</button></div>`;
  $('#qm').onclick=()=>{q=Math.max(1,q-1);draw()};$('#qp').onclick=()=>{q=Math.min(10,q+1);draw()};
  o.querySelectorAll('.opt').forEach(b=>b.onclick=()=>{meth=b.dataset.m;draw()});
  $('#cl').onclick=close;
  $('#go').onclick=async()=>{const b=$('#go');b.disabled=true;b.textContent=meth==='phonepe'?'Opening PhonePe…':'Placing order…';
   try{const r=await api('/orders',{method:'POST',body:{item_id:i.id,qty:q,method:meth}});meth==='phonepe'?wait(r):done(r)}
   catch(x){$('#pe').textContent=x.message;b.disabled=false;b.textContent=lbl}};
 };
 draw();
}
'''
a = h.index("/* payment */"); b = h.index("async function vOrd(){")
h = h[:a] + NEWPAY + h[b:]

swap("""<span class="tag ${x.status==='paid'?'':'am'}">${x.status==='paid'?'Paid online':'Pay at counter'}</span>""", "${stag(x)}")
swap("""${x.method==='online'?'Online '+esc(x.txn):'Cash'}""", """${x.method==='cash'?'Cash':'PhonePe '+esc(x.txn)}""")
swap("""${x.status==='paid'?'<span class="tag">Paid</span>':`<button class="btn" onclick="markPaid(${x.id})">Mark paid</button>`}""",
     """${x.status==='unpaid'?`<button class="btn" onclick="markPaid(${x.id})">Mark paid</button>`:stag(x)}""")

NEWMOCK = r""" if(p==='/orders'&&m==='POST'){const i=DB.menu.find(x=>x.id==b.item_id),q=+b.qty||1;if(i.stock<q)throw new Error('Only '+i.stock+' left of '+i.name+'.');if(b.method!=='cash'&&b.method!=='phonepe')throw new Error('Choose a payment method.');i.stock-=q;const id=DB.oid++,pp=b.method==='phonepe',status=pp?'pending':'unpaid';DB.orders.unshift({id,name:i.name,item:i.name,student:'Shweta',qty:q,total:q*i.price,created:new Date().toISOString().slice(0,19),method:b.method,status,txn:''});const r={ok:1,id,total:q*i.price,status,txn:''};if(pp)r.pay={vpa:'yourname@ybl',name:'SmartCanteen',note:'SmartCanteen order '+id};return r}
 if(/^\/orders\/\d+\/confirm$/.test(p)){const o=DB.orders.find(x=>x.id==p.split('/')[2]),u=String(b.utr||'').replace(/\s/g,'');if(!/^\d{12}$/.test(u))throw new Error('Enter the 12-digit UTR (reference number) shown in PhonePe.');o.status='paid';o.txn=u;return{ok:1,id:o.id,total:o.total,status:'paid',txn:u}}
 if(/^\/orders\/\d+\/cancel$/.test(p)){const o=DB.orders.find(x=>x.id==p.split('/')[2]);o.status='cancelled';DB.menu.find(i=>i.name===o.item).stock+=o.qty;return{ok:1}}
"""
h, n = re.subn(r"\n if\(p==='/orders'&&m==='POST'\)\{[^\n]*\n", lambda m: "\n" + NEWMOCK, h, count=1)
if n != 1:
    sys.exit("Could not find the demo-order line in index.html, nothing was changed.")
open(P, "w", encoding="utf-8").write(h)
print("Done. Payment now offers Cash and PhonePe. Backup: static/index.backup.html")
