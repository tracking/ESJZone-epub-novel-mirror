#!/bin/python3
# -*- coding: utf-8 -*-
import os
import subprocess
from datetime import datetime


def add_commit_push(inputFiles, num):
    now = datetime.now()
    # Git add
    subprocess.run(["git", "add"] + inputFiles)
    date = now.strftime("%Y-%m")
    # Git commit
    subprocess.run(["git", "commit", "-m", f"esjzone backup {date} |push {num}"])

    # Git push
    subprocess.run(["git", "push", "origin", "main"])


def get_files():
    try:
        subprocess.run(['git', 'config', '--global', 'core.quotepath', 'false'])
        subprocess.run(['git', 'config', 'core.quotepath', 'false'])
        # 使用git命令获取未跟踪文件列表
        result = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard'], capture_output=True, text=True)
        # 将结果按行分割成列表
        untracked_files = result.stdout.strip().split('\n')
        result2 = subprocess.run(['git', 'diff', '--name-only', '--diff-filter=d'], capture_output=True, text=True)

        # 将结果按行分割成列表
        unstaged_files2 = result2.stdout.strip().split('\n')
        return untracked_files + unstaged_files2
    except subprocess.CalledProcessError as e:
        print(f"Error while getting untracked files: {e}")
        return []


files = get_files()
for file_to_pack in files:
    file_size = os.path.getsize(file_to_pack)
    if file_size > 50 * 1024 * 1024:
        file_dir = os.path.dirname(file_to_pack)
        file_name = os.path.basename(file_to_pack)
        split_command = f"7z a -v40m \"{file_name}.7z\" {file_name}"
        subprocess.run(['7z', 'a', '-v40m', f"{file_name}.7z", file_name], text=True, cwd=file_dir)
files = get_files()
max_batch_size = 1 * 1024 * 1024 * 1024  # 1GB
files_cache = []
files_size = 0
push_count = 0
for file_to_add in files:
    if os.path.getsize(file_to_add) > 50 * 1024 * 1024:
        continue
    files_size += os.path.getsize(file_to_add)
    files_cache.append(file_to_add)
    if len(files_cache) >= 255 or files_size > max_batch_size:
        add_commit_push(files_cache, push_count)
        files_cache = []
        files_size = 0
        push_count += 1
add_commit_push(files_cache, push_count)
