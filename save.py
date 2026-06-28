import os
import fnmatch

def export_python_files_to_txt(root_dir, output_file="project_export.txt"):
    """
    تمام فایل‌های پایتون (.py) را در تمام پوشه‌های زیرمجموعه پیدا کرده،
    و محتوای آنها را به همراه نام فایل در یک فایل متنی ذخیره می‌کند.
    """
    # پوشه‌هایی که نمی‌خواهیم محتوایشان را بگیریم (اختیاری)
    exclude_dirs = {".git", "__pycache__", "logs", "output", "reports", "tests"} # می‌توانید این لیست را ویرایش کنید

    with open(output_file, "w", encoding="utf-8") as outfile:
        outfile.write("=" * 80 + "\n")
        outfile.write(f"EXPORT OF ALL PYTHON FILES FROM: {os.path.abspath(root_dir)}\n")
        outfile.write("=" * 80 + "\n\n")

        # os.walk همه پوشه‌ها و زیرپوشه‌ها را پیمایش می‌کند
        for dirpath, dirnames, filenames in os.walk(root_dir):
            # پوشه‌های ناخواسته را از پیمایش حذف می‌کنیم (برای جلوگیری از هدررفت زمان)
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]

            # فایل‌های پایتون را در پوشه جاری پیدا می‌کنیم
            py_files = [f for f in filenames if f.endswith(".py")]

            for filename in py_files:
                file_path = os.path.join(dirpath, filename)
                relative_path = os.path.relpath(file_path, root_dir)

                # اطلاعات فایل را در فایل خروجی می‌نویسیم
                outfile.write(f"\n{'=' * 80}\n")
                outfile.write(f"FILE: {relative_path}\n")
                outfile.write(f"{'=' * 80}\n\n")

                try:
                    # فایل را با encoding utf-8 خوانده و محتوا را می‌نویسیم
                    with open(file_path, "r", encoding="utf-8") as infile:
                        content = infile.read()
                        outfile.write(content)
                        if not content.endswith("\n"):
                            outfile.write("\n")  # در صورت نیاز یک خط جدید اضافه می‌کنیم
                except Exception as e:
                    outfile.write(f"!!! ERROR: Could not read file - {e}\n")
                outfile.write("\n")  # یک خط فاصله بین فایل‌ها

    print(f"✅ تمام فایل‌های پایتون با موفقیت در فایل '{output_file}' ذخیره شدند.")
    print(f"📁 مسیر فایل: {os.path.abspath(output_file)}")


# --- اجرای اسکریپت ---
if __name__ == "__main__":
    # '.' یعنی پوشه جاری که اسکریپت در آن قرار دارد.
    # اگر می‌خواهید از پوشه دیگری شروع کنید، مسیر آن را بنویسید.
    project_directory = "."
    export_python_files_to_txt(project_directory)