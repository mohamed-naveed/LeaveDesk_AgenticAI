from datetime import timedelta
from database.models import Holiday

class CalendarAgent:
    """
    Calendar Agent
    Responsibility: Calculates working days, weekends, and holidays.
    """
    def execute(
        self,
        start_date,
        end_date,
        db
    ):
        holidays = (
            db.query(Holiday)
            .filter(
                Holiday.HolidayDate >= start_date,
                Holiday.HolidayDate <= end_date
            )
            .all()
        )

        holiday_dates = {
            h.HolidayDate
            for h in holidays
        }

        working_days = 0
        weekends = 0
        holiday_count = 0
        day_details = []

        current = start_date

        while current <= end_date:
            is_weekend = current.weekday() >= 5
            is_holiday = current in holiday_dates
            if is_weekend:
                weekends += 1
            elif is_holiday:
                holiday_count += 1
            else:
                working_days += 1
            
            day_details.append({
                "date": current,
                "is_weekend": is_weekend,
                "is_holiday": is_holiday,
                "day_type": "FullDay",
                "leave_days": 0.0 if (is_weekend or is_holiday) else 1.0
            })
            current += timedelta(days=1)

        return {
            "working_days": working_days,
            "weekends": weekends,
            "holidays": holiday_count,
            "days": day_details
        }
