import pandas as pd
from mongodb import MongoDB
import datetime


def convert_to_date(date_string):
    return datetime.datetime.strptime(date_string, "%d %b %Y")


def convert_to_number(number_string):
    return float(number_string.replace(",", "")) if number_string else 0.0


def read_expense_sheet(file_path):
    db = MongoDB().db
    t_file_path = "files/t_sheet.csv"
    with open(file_path, "r") as fin:
        data = fin.read().splitlines(True)
    with open(t_file_path, "w") as fout:
        fout.writelines(data[20:])

    df = pd.read_csv(t_file_path, sep="	", header=None, keep_default_na=False)

    for r in df.values:
        if len(r) < 7:
            print("Skipped this row", r)
            continue
        trn_date = r[0].strip()
        description = r[2].strip()
        ref_number = r[3].strip()
        debit_amount = r[4].strip()
        credit_amount = r[5].strip()
        balance = r[6].strip()

        if not trn_date or (not debit_amount and not credit_amount):
            print("Skipped due to invalid values", r)
            continue
        insert_dict = {
            "trn_date": convert_to_date(trn_date),
            "description": description,
            "ref_number": ref_number,
            "debit_amount": convert_to_number(debit_amount),
            "credit_amount": convert_to_number(credit_amount),
            "balance": convert_to_number(balance)
        }
        db.expense.update_one(
            insert_dict,
            {
                "$set": insert_dict
            },
            upsert=True
        )


def main():
    for i in range(4):
        read_expense_sheet(f"files/expense_sheet_{i+1}.xls")


if __name__ == "__main__":
    main()
