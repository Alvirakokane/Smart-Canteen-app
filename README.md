# SmartCanteen: Canteen Demand Prediction System

Stack: HTML/CSS/JS frontend, Python Flask API, SQLite database.

## Run
1. Install Python 3.10+
2. `pip install -r requirements.txt`
3. `python app.py`
4. Open http://localhost:5000

Demo logins
- Student: student@canteen.edu / student123
- Admin: admin@canteen.edu / admin123

## How the parts connect
Browser (static/index.html) -> fetch /api/* -> app.py -> canteen.db
Each student order is saved and also added to the sales history, so the
next-day forecast improves automatically. Admin can import more history as CSV
(Date, Food Item, Quantity Sold, Price) and apply the forecast to stock.

## Prediction model
predicted = 0.5 x same-weekday average + 0.5 x last-7-day average
prepare = predicted x (1 + safety margin 10%)

## Next steps
Excel upload, QR ordering, SMS/email alerts, scikit-learn or Prophet model, deployment on Render or PythonAnywhere.

## v2 additions
- Student: QR scanner (camera + jsQR) shows calories, protein, carbs, fat, fiber and ingredients.
- Admin: Analytics page, QR code generator for every dish, nutrition fields on the menu form.
- ML forecast: weekday seasonality + linear trend, confidence from in-sample error (pure Python).
- Power BI: Analytics > Export for Power BI downloads smartcanteen_powerbi.csv.
  Power BI Desktop > Get data > Text/CSV > Load. Suggested visuals: line (Date, Revenue), donut (Category), matrix (Weekday x Food Item).
- If you ran the old version, delete canteen.db once. The app rebuilds it automatically.

## v3: real photos and payment
- Order now opens a payment sheet: quantity, then Cash (pay at counter) or Online (UPI ID).
  The order is created only after you confirm. Online payment is simulated; replace the txn line
  in app.py `order()` with Razorpay/Paytm verification for real money.
- Admin > Orders lists every order. Cash orders stay "unpaid" until you press Mark paid.
- Photos: Admin > Menu > Upload photo for each dish (JPG/PNG/WebP under 2 MB).
  Until a photo exists the emoji is shown. You can also drop files in static/img/ named like
  misal-pav.jpg, vada-pav.jpg, poha.jpg, veg-biryani.jpg, masala-dosa.jpg, dal-tadka-rice.jpg.
- Delete canteen.db once if you ran an older version; it rebuilds automatically.
