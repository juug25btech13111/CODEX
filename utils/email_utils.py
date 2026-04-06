import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, formatdate

def send_smtp_email(to_email, subject, html_content, text_content=None, priority="normal"):
    """
    Sends a professional enterprise-grade email using standard SMTP.
    Works in both local and production environments.
    
    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_content: HTML body of the email
        text_content: Plain text fallback (optional)
        priority: 'high', 'normal', or 'low' — controls email importance headers
    """
    mail_server = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    mail_port = int(os.environ.get("MAIL_PORT", 587))
    mail_username = os.environ.get("MAIL_USERNAME")
    mail_password = os.environ.get("MAIL_PASSWORD")
    
    if not mail_username or not mail_password:
        print("[SMTP] ERROR: MAIL_USERNAME and MAIL_PASSWORD are not set in .env", flush=True)
        return False
        
    # Ensure variables are treated as str for type checking
    mail_user: str = mail_username or ""
    mail_pass: str = mail_password or ""
    
    sender_email = os.environ.get("MAIL_DEFAULT_SENDER", mail_user)
    if not sender_email:
        sender_email = mail_user
        
    print(f"[SMTP] Preparing to send email from {sender_email} to: {to_email}", flush=True)
    
    # Build the MIME message
    msg = MIMEMultipart("alternative")
    
    # --- Professional Email Headers ---
    msg["From"] = formataddr(("NeuroSent Platform", sender_email))
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Reply-To"] = formataddr(("NeuroSent Support", sender_email))
    msg["X-Mailer"] = "NeuroSent Notification Engine v2.0"
    msg["X-Auto-Response-Suppress"] = "OOF, DR, RN, NRN, AutoReply"
    msg["Precedence"] = "bulk"
    
    # Priority headers (makes email appear as important in Gmail/Outlook)
    if priority == "high":
        msg["X-Priority"] = "1"             # 1 = Highest
        msg["X-MSMail-Priority"] = "High"   # Outlook
        msg["Importance"] = "high"           # RFC 2156
    elif priority == "low":
        msg["X-Priority"] = "5"
        msg["X-MSMail-Priority"] = "Low"
        msg["Importance"] = "low"
    else:
        msg["X-Priority"] = "3"
        msg["X-MSMail-Priority"] = "Normal"
        msg["Importance"] = "normal"
    
    # Attach content parts
    if text_content:
        part1 = MIMEText(text_content, "plain", "utf-8")
        msg.attach(part1)
        
    if html_content:
        part2 = MIMEText(html_content, "html", "utf-8")
        msg.attach(part2)
        
    try:
        # Connect to the server with a timeout
        server = smtplib.SMTP(mail_server, mail_port, local_hostname='localhost', timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(mail_user, mail_pass)
        
        # Send the email
        server.send_message(msg)
        server.quit()
        
        print(f"[SMTP] Successfully sent email to {to_email}", flush=True)
        return True
    except (smtplib.SMTPException, OSError, Exception) as e:
        print(f"[SMTP] Failed to send email via SMTP: {type(e).__name__}: {e}", flush=True)
        return False
