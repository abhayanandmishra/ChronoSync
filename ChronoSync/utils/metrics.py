import os

def count_files_and_size(path, file_types):
    count, total_size = 0, 0
    for root, _, files in os.walk(path):
        for file in files:
            if any(file.endswith(ext) for ext in file_types):
                count += 1
                total_size += os.path.getsize(os.path.join(root, file))
    return count, total_size
