"""Parsing for ACARS H1-label flight-initialization ("#MDINI"/"INI") messages.

These are downlink messages military/AMC aircraft send to open a flight
session with a ground station, of the form:

    - #MDINI/ID44129A RCH268 PAM306410163/MR0 0/AFPHNL PGWT/TD132140 00509B35
    INI/ID15734T,RCH403,GJZF710QJ198/MR0,1/AFKLRF,KHRT/TD171245,1245011F

Fields are separated by either spaces or commas depending on the source.
"""

import re

FLIGHT_INIT_LABEL = "H1"

MDINI_PATTERN = re.compile(
    r"""
    ^\s*(?:-\s*)?
    \#?(?:MDINI|INI)/ID(?P<flight_num>\d+)(?P<flight_suffix>[A-Z]?)
    [\s,]+(?P<callsign>[A-Z0-9]+)
    [\s,]+(?P<dataref>[A-Z0-9]+)/MR(?P<mr>\d+)
    [\s,]+(?P<dep_seq>\d+)/AF(?P<departure>[A-Z0-9]+)
    [\s,]+(?P<arrival>[A-Z0-9]+)/TD(?P<date_day>\d{2})(?P<time>\d{2,4})
    [\s,]+(?P<trailer>[A-Z0-9]+)
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)


def is_flight_init_label(label):
    return str(label or "").strip().upper() == FLIGHT_INIT_LABEL


def parse_flight_init_text(text):
    """Parse an MDINI/INI flight-initialization text body.

    Returns None if the text doesn't match the expected grammar (e.g. other
    H1 message subtypes such as OOOI reports).
    """
    if not text:
        return None

    match = MDINI_PATTERN.match(text.strip())
    if not match:
        return None

    fields = match.groupdict()
    return {
        "flight_init_id": fields["flight_num"] + fields["flight_suffix"].upper(),
        "callsign": fields["callsign"].upper(),
        "dataref": fields["dataref"].upper(),
        "mr": fields["mr"],
        "departure": fields["departure"].upper(),
        "arrival": fields["arrival"].upper(),
        "date_day": fields["date_day"],
        "time": fields["time"],
        "trailer": fields["trailer"].upper(),
    }


def parse_flight_init_message(message):
    """Parse a message dict, returning flight-init fields only when the
    message is label H1 and its text matches the MDINI/INI grammar."""
    if not isinstance(message, dict):
        return None
    if not is_flight_init_label(message.get("label")):
        return None
    return parse_flight_init_text(message.get("text"))
