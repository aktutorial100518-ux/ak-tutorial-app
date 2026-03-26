from flask import Flask, render_template, request, redirect, send_file
from xhtml2pdf import pisa
from io import BytesIO
import os
import sqlite3
from datetime import datetime
import pandas as pd

app = Flask(__name__)

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB = "fees.db"

# Database connection
def get_db():
    return sqlite3.connect(DB)

# PDF helper
def create_pdf(html):
    result = BytesIO()
    pisa.CreatePDF(html, dest=result)
    result.seek(0)
    return result

# Initialize database
def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS students(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        class_name TEXT,
        parent TEXT,
        mobile TEXT,
        total_fees REAL,
        photo TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        amount REAL,
        date TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS attendance(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        date TEXT,
        status TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS tests(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        subject TEXT,
        marks INTEGER,
        total INTEGER,
        date TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS finance(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        description TEXT,
        amount REAL,
        date TEXT
    )
    """)

    conn.commit()
    conn.close()


# Dashboard
@app.route("/")
def dashboard():
    conn = get_db()
    c = conn.cursor()

    # Total students
    c.execute("SELECT COUNT(*) FROM students")
    students = c.fetchone()[0]

    # Fees collected
    c.execute("SELECT IFNULL(SUM(amount),0) FROM payments")
    collected = c.fetchone()[0]

    # Total fees
    c.execute("SELECT IFNULL(SUM(total_fees),0) FROM students")
    total = c.fetchone()[0]

    # Pending fees
    pending = total - collected

    # Finance summary
    c.execute("SELECT IFNULL(SUM(amount),0) FROM finance WHERE type='Income'")
    total_income = c.fetchone()[0]

    c.execute("SELECT IFNULL(SUM(amount),0) FROM finance WHERE type='Expense'")
    total_expense = c.fetchone()[0]

    profit = total_income - total_expense

    # Today's collection
    today_date = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT IFNULL(SUM(amount),0) FROM payments WHERE date=?", (today_date,))
    today_collection = c.fetchone()[0]

    # This month collection
    current_month = datetime.now().strftime("%Y-%m")
    c.execute("SELECT IFNULL(SUM(amount),0) FROM payments WHERE substr(date,1,7)=?", (current_month,))
    month_collection = c.fetchone()[0]

    # Pending students count
    c.execute("""
        SELECT COUNT(*) FROM (
            SELECT s.id
            FROM students s
            LEFT JOIN payments p ON s.id = p.student_id
            GROUP BY s.id, s.total_fees
            HAVING s.total_fees - IFNULL(SUM(p.amount),0) > 0
        )
    """)
    pending_students = c.fetchone()[0]

    # Topper student
    c.execute("""
        SELECT s.name,
               SUM(t.marks) as total_marks,
               SUM(t.total) as total_outof,
               ROUND((SUM(t.marks) * 100.0 / SUM(t.total)), 2) as percentage
        FROM tests t
        JOIN students s ON s.id = t.student_id
        GROUP BY s.id, s.name
        ORDER BY percentage DESC
        LIMIT 1
    """)
    topper = c.fetchone()

    # Recent payments
    c.execute("""
        SELECT s.name, p.amount, p.date
        FROM payments p
        JOIN students s ON s.id = p.student_id
        ORDER BY p.id DESC
        LIMIT 5
    """)
    recent_payments = c.fetchall()

    # Recent finance entries
    c.execute("""
        SELECT type, description, amount, date
        FROM finance
        ORDER BY id DESC
        LIMIT 5
    """)
    recent_finance = c.fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        students=students,
        collected=collected,
        pending=pending,
        total_income=total_income,
        total_expense=total_expense,
        profit=profit,
        today_collection=today_collection,
        month_collection=month_collection,
        pending_students=pending_students,
        topper=topper,
        recent_payments=recent_payments,
        recent_finance=recent_finance
    )

# Students Page
@app.route("/students", methods=["GET", "POST"])
def students():
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        name = request.form["name"]
        class_name = request.form["class_name"]
        parent = request.form["parent"]
        mobile = request.form["mobile"]
        total_fees = request.form["total_fees"]

        photo_file = request.files["photo"]
        photo_name = ""

        if photo_file and photo_file.filename:
            photo_name = photo_file.filename
            photo_path = os.path.join(app.config["UPLOAD_FOLDER"], photo_name)
            photo_file.save(photo_path)

        c.execute(
            "INSERT INTO students(name,class_name,parent,mobile,total_fees,photo) VALUES(?,?,?,?,?,?)",
            (name, class_name, parent, mobile, total_fees, photo_name)
        )
        conn.commit()

    search = request.args.get("search")

    if search:
        c.execute(
            "SELECT * FROM students WHERE name LIKE ? OR mobile LIKE ?",
            ('%' + search + '%', '%' + search + '%')
        )
    else:
        c.execute("SELECT * FROM students")

    data = c.fetchall()
    conn.close()

    return render_template("students.html", students=data)


# Payment Page
@app.route("/payment/<int:sid>", methods=["GET", "POST"])
def payment(sid):
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        amount = request.form["amount"]

        c.execute(
            "INSERT INTO payments(student_id,amount,date) VALUES(?,?,?)",
            (sid, amount, datetime.now().strftime("%Y-%m-%d"))
        )
        conn.commit()

    c.execute("SELECT * FROM payments WHERE student_id=?", (sid,))
    payments = c.fetchall()

    c.execute("SELECT total_fees FROM students WHERE id=?", (sid,))
    total_fees = c.fetchone()[0]

    c.execute("SELECT IFNULL(SUM(amount),0) FROM payments WHERE student_id=?", (sid,))
    paid = c.fetchone()[0]

    pending = total_fees - paid

    conn.close()

    return render_template(
        "payments.html",
        payments=payments,
        sid=sid,
        total_fees=total_fees,
        paid=paid,
        pending=pending
    )

@app.route("/payments")
def payments_summary():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT 
            s.id,
            s.name,
            s.class_name,
            s.total_fees,
            IFNULL(SUM(p.amount), 0) as paid,
            s.total_fees - IFNULL(SUM(p.amount), 0) as pending
        FROM students s
        LEFT JOIN payments p ON s.id = p.student_id
        GROUP BY s.id, s.name, s.class_name, s.total_fees
        ORDER BY s.name
    """)
    records = c.fetchall()

    conn.close()

    return render_template("payments_summary.html", records=records)


@app.route("/receipt/<int:sid>")
def receipt(sid):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM students WHERE id=?", (sid,))
    student = c.fetchone()

    c.execute("SELECT * FROM payments WHERE student_id=? ORDER BY id DESC LIMIT 1", (sid,))
    payment = c.fetchone()

    receipt_no = f"AKT-{payment[0]:04d}" if payment else ""
    month = datetime.now().strftime("%B %Y")

    conn.close()

    return render_template(
        "receipt.html",
        student=student,
        payment=payment,
        receipt_no=receipt_no,
        month=month
    )


@app.route("/receipt_pdf/<int:sid>")
def receipt_pdf(sid):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM students WHERE id=?", (sid,))
    student = c.fetchone()

    c.execute("SELECT * FROM payments WHERE student_id=? ORDER BY id DESC LIMIT 1", (sid,))
    payment = c.fetchone()

    receipt_no = f"AKT-{payment[0]:04d}" if payment else ""
    month = datetime.now().strftime("%B %Y")

    conn.close()

    html = render_template(
        "receipt.html",
        student=student,
        payment=payment,
        receipt_no=receipt_no,
        month=month
    )

    pdf = create_pdf(html)

    return send_file(
        pdf,
        download_name=f"receipt_{sid}.pdf",
        as_attachment=True,
        mimetype="application/pdf"
    )


@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        student_id = request.form["student_id"]
        status = request.form["status"]

        c.execute(
            "INSERT INTO attendance(student_id,date,status) VALUES(?,?,?)",
            (student_id, datetime.now().strftime("%Y-%m-%d"), status)
        )
        conn.commit()

    c.execute("SELECT * FROM attendance")
    records = c.fetchall()

    conn.close()

    return render_template("attendance.html", records=records)


@app.route("/tests", methods=["GET", "POST"])
def tests():
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        student_id = request.form["student_id"]
        subject = request.form["subject"]
        marks = request.form["marks"]
        total = request.form["total"]

        c.execute(
            "INSERT INTO tests(student_id, subject, marks, total, date) VALUES(?,?,?,?,?)",
            (student_id, subject, marks, total, datetime.now().strftime("%Y-%m-%d"))
        )
        conn.commit()

    c.execute("SELECT * FROM tests")
    records = c.fetchall()

    conn.close()

    return render_template("tests.html", records=records)


@app.route("/finance", methods=["GET", "POST"])
def finance():
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        type = request.form["type"]
        description = request.form["description"]
        amount = request.form["amount"]

        c.execute(
            "INSERT INTO finance(type,description,amount,date) VALUES(?,?,?,?)",
            (type, description, amount, datetime.now().strftime("%Y-%m-%d"))
        )
        conn.commit()

    # Finance records
    c.execute("SELECT * FROM finance ORDER BY id DESC")
    records = c.fetchall()

    # Total Income
    c.execute("SELECT IFNULL(SUM(amount),0) FROM finance WHERE type='Income'")
    total_income = c.fetchone()[0]

    # Total Expense
    c.execute("SELECT IFNULL(SUM(amount),0) FROM finance WHERE type='Expense'")
    total_expense = c.fetchone()[0]

    # Profit
    profit = total_income - total_expense

    # Student fee summary
    c.execute("SELECT IFNULL(SUM(total_fees),0) FROM students")
    total_student_fees = c.fetchone()[0]

    c.execute("SELECT IFNULL(SUM(amount),0) FROM payments")
    total_fees_collected = c.fetchone()[0]

    total_fees_pending = total_student_fees - total_fees_collected

    # Monthly report
    c.execute("""
        SELECT 
            substr(date, 1, 7) as month,
            SUM(CASE WHEN type='Income' THEN amount ELSE 0 END) as income,
            SUM(CASE WHEN type='Expense' THEN amount ELSE 0 END) as expense
        FROM finance
        GROUP BY substr(date, 1, 7)
        ORDER BY month DESC
    """)
    monthly_report = c.fetchall()

    # Yearly report
    c.execute("""
        SELECT 
            substr(date, 1, 4) as year,
            SUM(CASE WHEN type='Income' THEN amount ELSE 0 END) as income,
            SUM(CASE WHEN type='Expense' THEN amount ELSE 0 END) as expense
        FROM finance
        GROUP BY substr(date, 1, 4)
        ORDER BY year DESC
    """)
    yearly_report = c.fetchall()

    conn.close()

    return render_template(
        "finance.html",
        records=records,
        total_income=total_income,
        total_expense=total_expense,
        profit=profit,
        monthly_report=monthly_report,
        yearly_report=yearly_report,
        total_student_fees=total_student_fees,
        total_fees_collected=total_fees_collected,
        total_fees_pending=total_fees_pending
    )


@app.route("/edit_finance/<int:fid>", methods=["GET", "POST"])
def edit_finance(fid):
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        type = request.form["type"]
        description = request.form["description"]
        amount = request.form["amount"]

        c.execute(
            "UPDATE finance SET type=?, description=?, amount=? WHERE id=?",
            (type, description, amount, fid)
        )
        conn.commit()
        conn.close()
        return redirect("/finance")

    c.execute("SELECT * FROM finance WHERE id=?", (fid,))
    record = c.fetchone()

    conn.close()

    return render_template("edit_finance.html", record=record)


@app.route("/delete_finance/<int:fid>")
def delete_finance(fid):
    conn = get_db()
    c = conn.cursor()

    c.execute("DELETE FROM finance WHERE id=?", (fid,))
    conn.commit()
    conn.close()

    return redirect("/finance")


@app.route("/whatsapp/<int:sid>")
def whatsapp(sid):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM students WHERE id=?", (sid,))
    student = c.fetchone()

    conn.close()

    if student:
        mobile = student[4]
        name = student[1]
        fees = student[5]

        message = f"A.K. Tutorial Fee Reminder%0ADear Parent,%0A{name}'s fees of Rs. {fees} is pending.%0APlease pay at the earliest.%0AThank you."
        whatsapp_link = f"https://wa.me/91{mobile}?text={message}"

        return redirect(whatsapp_link)

    return "Student not found"


@app.route("/export_students")
def export_students():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id, name, class_name, parent, mobile, total_fees FROM students")
    data = c.fetchall()

    conn.close()

    df = pd.DataFrame(data, columns=["ID", "Name", "Class", "Parent", "Mobile", "Fees"])
    df.to_excel("students_report.xlsx", index=False)

    return "Excel file created: students_report.xlsx"


@app.route("/pending_fees")
def pending_fees():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT s.id, s.name, s.class_name, s.parent, s.mobile, s.total_fees,
               IFNULL(SUM(p.amount), 0) as paid,
               s.total_fees - IFNULL(SUM(p.amount), 0) as pending
        FROM students s
        LEFT JOIN payments p ON s.id = p.student_id
        GROUP BY s.id, s.name, s.class_name, s.parent, s.mobile, s.total_fees
        HAVING pending > 0
        ORDER BY pending DESC
    """)
    records = c.fetchall()

    pending_students_count = len(records)
    total_pending_amount = sum(r[7] for r in records) if records else 0

    conn.close()

    return render_template(
        "pending_fees.html",
        records=records,
        pending_students_count=pending_students_count,
        total_pending_amount=total_pending_amount
    )

@app.route("/edit_student/<int:sid>", methods=["GET", "POST"])
def edit_student(sid):
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        name = request.form["name"]
        class_name = request.form["class_name"]
        parent = request.form["parent"]
        mobile = request.form["mobile"]
        total_fees = request.form["total_fees"]

        photo = request.files.get("photo")

        if photo and photo.filename != "":
            path = os.path.join("static/uploads", photo.filename)
            photo.save(path)

            c.execute(
                "UPDATE students SET name=?, class_name=?, parent=?, mobile=?, total_fees=?, photo=? WHERE id=?",
                (name, class_name, parent, mobile, total_fees, photo.filename, sid)
            )
        else:
            c.execute(
                "UPDATE students SET name=?, class_name=?, parent=?, mobile=?, total_fees=? WHERE id=?",
                (name, class_name, parent, mobile, total_fees, sid)
            )

        conn.commit()
        conn.close()
        return redirect("/students")

    c.execute("SELECT * FROM students WHERE id=?", (sid,))
    student = c.fetchone()

    conn.close()

    return render_template("edit_student.html", student=student)


@app.route("/delete_student/<int:sid>")
def delete_student(sid):
    conn = get_db()
    c = conn.cursor()

    c.execute("DELETE FROM students WHERE id=?", (sid,))
    conn.commit()
    conn.close()

    return redirect("/students")


@app.route("/edit_payment/<int:pid>", methods=["GET", "POST"])
def edit_payment(pid):
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        amount = request.form["amount"]

        c.execute("UPDATE payments SET amount=? WHERE id=?", (amount, pid))
        conn.commit()

        c.execute("SELECT student_id FROM payments WHERE id=?", (pid,))
        student = c.fetchone()

        conn.close()

        return redirect("/payment/" + str(student[0]))

    c.execute("SELECT * FROM payments WHERE id=?", (pid,))
    payment = c.fetchone()

    conn.close()

    return render_template("edit_payment.html", payment=payment)


@app.route("/edit_attendance/<int:aid>", methods=["GET", "POST"])
def edit_attendance(aid):
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        status = request.form["status"]

        c.execute("UPDATE attendance SET status=? WHERE id=?", (status, aid))
        conn.commit()
        conn.close()

        return redirect("/attendance")

    c.execute("SELECT * FROM attendance WHERE id=?", (aid,))
    record = c.fetchone()

    conn.close()

    return render_template("edit_attendance.html", record=record)


@app.route("/student_profile/<int:sid>")
def student_profile(sid):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM students WHERE id=?", (sid,))
    student = c.fetchone()

    c.execute("SELECT * FROM payments WHERE student_id=?", (sid,))
    payments = c.fetchall()

    c.execute("SELECT IFNULL(SUM(amount),0) FROM payments WHERE student_id=?", (sid,))
    paid = c.fetchone()[0]

    total_fees = student[5]
    pending = total_fees - paid

    c.execute("SELECT * FROM attendance WHERE student_id=?", (sid,))
    attendance = c.fetchall()

    c.execute("SELECT * FROM tests WHERE student_id=?", (sid,))
    tests = c.fetchall()

    conn.close()

    return render_template(
        "student_profile.html",
        student=student,
        payments=payments,
        paid=paid,
        pending=pending,
        attendance=attendance,
        tests=tests
    )

@app.route("/performance")
def performance():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT s.name, t.subject, t.marks, t.total
        FROM tests t
        JOIN students s ON s.id = t.student_id
    """)
    data = c.fetchall()

    report = {}

    for name, subject, marks, total in data:
        if name not in report:
            report[name] = {"marks": 0, "total": 0}

        report[name]["marks"] += marks
        report[name]["total"] += total

    result = []

    for name, val in report.items():
        percentage = (val["marks"] / val["total"]) * 100 if val["total"] > 0 else 0
        result.append((name, val["marks"], val["total"], round(percentage, 2)))

    result.sort(key=lambda x: x[3], reverse=True)

    students_tested = len(result)

    if students_tested > 0:
        topper = result[0]
        average_percentage = round(sum(r[3] for r in result) / students_tested, 2)
    else:
        topper = None
        average_percentage = 0

    conn.close()

    return render_template(
        "performance.html",
        report=result,
        topper=topper,
        average_percentage=average_percentage,
        students_tested=students_tested
    )

@app.route("/export_pending")
def export_pending():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT s.name, s.class_name, s.parent, s.mobile,
               s.total_fees,
               IFNULL(SUM(p.amount), 0) as paid,
               s.total_fees - IFNULL(SUM(p.amount), 0) as pending
        FROM students s
        LEFT JOIN payments p ON s.id = p.student_id
        GROUP BY s.id
        HAVING pending > 0
    """)

    data = c.fetchall()
    conn.close()

    df = pd.DataFrame(data, columns=[
        "Name", "Class", "Parent", "Mobile",
        "Total Fees", "Paid", "Pending"
    ])

    file_name = "pending_fees_report.xlsx"
    df.to_excel(file_name, index=False)

    return send_file(file_name, as_attachment=True)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)