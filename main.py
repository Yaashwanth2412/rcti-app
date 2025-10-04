from fastapi import FastAPI, Depends, UploadFile, File
from sqlalchemy.orm import Session
import pandas as pd
import models, database
from pydantic import BaseModel

# Initialize FastAPI app
app = FastAPI()

# Create tables (if not already created)
models.Base.metadata.create_all(bind=database.engine)

# Dependency to get DB session
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------------
# Routes
# ----------------------

# Home route
@app.get("/")
def home():
    return {"msg": "RCTI App Running!"}


# Upload CSV route
@app.post("/upload_csv/")
def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    df = pd.read_csv(file.file)  # read the uploaded CSV
    for _, row in df.iterrows():
        client = models.Client(name=row["name"], email=row["email"])
        db.add(client)
    db.commit()
    return {"msg": "CSV imported into Clients table"}


# ----------------------
# Create Invoice Section
# ----------------------

# Define request body with Pydantic
class InvoiceCreate(BaseModel):
    client_id: int
    amount: float
    tax: float

@app.post("/create_invoice/")
def create_invoice(invoice: InvoiceCreate, db: Session = Depends(get_db)):
    total = invoice.amount + invoice.tax
    new_invoice = models.Invoice(
        client_id=invoice.client_id,
        amount=invoice.amount,
        tax=invoice.tax,
        total=total
    )
    db.add(new_invoice)
    db.commit()
    db.refresh(new_invoice)  # fetch inserted invoice

    return {
        "msg": "Invoice created successfully",
        "id": new_invoice.id,
        "client_id": new_invoice.client_id,
        "amount": new_invoice.amount,
        "tax": new_invoice.tax,
        "total": new_invoice.total
    }

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

@app.post("/email_invoice/{invoice_id}")
def email_invoice(invoice_id: int, db: Session = Depends(database.SessionLocal)):
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        return {"error": "Invoice not found"}
    
    client = db.query(models.Client).filter(models.Client.id == invoice.client_id).first()

    # Generate the PDF first (reuse Step 4 code)
    pdf_filename = f"invoice_{invoice.id}.pdf"
    if not os.path.exists(pdf_filename):
        # generate if missing
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt="Invoice", ln=True, align="C")
        pdf.ln(10)
        pdf.cell(200, 10, txt=f"Invoice ID: {invoice.id}", ln=True)
        pdf.cell(200, 10, txt=f"Client: {client.name} ({client.email})", ln=True)
        pdf.cell(200, 10, txt=f"Amount: {invoice.amount}", ln=True)
        pdf.cell(200, 10, txt=f"Tax: {invoice.tax}", ln=True)
        pdf.cell(200, 10, txt=f"Total: {invoice.total}", ln=True)
        pdf.output(pdf_filename)

    # Email Config (use your Gmail / SMTP credentials here)
    sender_email = "your_email@gmail.com"
    receiver_email = client.email
    password = "your_app_password"   # Use Gmail App Password (not your Gmail password)

    # Build the email
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = f"Invoice #{invoice.id}"

    body = f"""
    Dear {client.name},

    Please find attached your invoice #{invoice.id}.

    Amount: {invoice.amount}
    Tax: {invoice.tax}
    Total: {invoice.total}

    Regards,
    RCTI Team
    """
    msg.attach(MIMEText(body, 'plain'))

    # Attach PDF
    with open(pdf_filename, "rb") as f:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename={pdf_filename}')
        msg.attach(part)

    try:
        # Send Email via Gmail SMTP
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, password)
        server.send_message(msg)
        server.quit()
        return {"msg": f"Invoice emailed to {client.email}"}
    except Exception as e:
        return {"error": str(e)}
