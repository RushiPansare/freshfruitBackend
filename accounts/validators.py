import re

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,49}$")
CITY_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,59}$")
EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
PHONE_RE = re.compile(r'^[6-9][0-9]{9}$')
PINCODE_RE = re.compile(r'^[1-9][0-9]{5}$')


def password_issues(pw):
    issues = []
    if len(pw) < 8:
        issues.append('at least 8 characters')
    if len(pw) > 64:
        issues.append('no more than 64 characters')
    if not re.search(r'[A-Z]', pw):
        issues.append('1 uppercase letter (A-Z)')
    if not re.search(r'[a-z]', pw):
        issues.append('1 lowercase letter (a-z)')
    if not re.search(r'[0-9]', pw):
        issues.append('1 number (0-9)')
    if not re.search(r'[^A-Za-z0-9\s]', pw):
        issues.append('1 special character (! @ # $ % ...)')
    if re.search(r'\s', pw):
        issues.append('no spaces')
    return issues


def password_error(pw):
    issues = password_issues(pw)
    if not issues:
        return ''
    if len(issues) == 1:
        text = issues[0]
    else:
        text = ', '.join(issues[:-1]) + ' and ' + issues[-1]
    return 'Password must contain ' + text


def check_name(v, label='Name'):
    if not NAME_RE.match(v or ''):
        return label + ' must be 2 to 50 letters (letters, spaces, . - only)'
    return ''


def check_city(v):
    if not CITY_RE.match(v or ''):
        return 'City must be 2 to 60 letters (letters, spaces, . - only)'
    return ''


def check_email(v):
    if not v or len(v) > 254 or not EMAIL_RE.match(v):
        return 'Enter a valid email address (example: name@gmail.com)'
    return ''


def check_phone(v):
    if not PHONE_RE.match(v or ''):
        return 'Enter a valid 10 digit mobile number starting with 6, 7, 8 or 9'
    return ''


def check_pincode(v):
    if not PINCODE_RE.match(v or ''):
        return 'Pincode must be exactly 6 digits and cannot start with 0'
    return ''