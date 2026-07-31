import os
import sys
import subprocess
import tempfile
import shutil
import requests
import zipfile
import dearpygui.dearpygui as dpg
from pathlib import Path
import threading
import json

class UpdateManager:
    def __init__(self, current_version, app_root):
        """
        初始化更新管理器
        
        Args:
            repo_owner: GitHub仓库所有者
            repo_name: 仓库名称
            current_version: 当前版本号
            app_root: 应用程序根目录
        """
        self.repo_owner = 'hangyu-yu'
        self.repo_name = 'EISAP'
        self.current_version = current_version
        self.app_root = Path(app_root)
        self.latest_version = None
        self.update_available = False
        self.is_updating = False
        
    def check_for_updates(self):
        """检查是否有可用更新"""
        try:
            # 获取最新发布版本信息
            url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                release_info = response.json()
                self.latest_version = release_info['tag_name']
                
                # 简单版本比较
                if self.latest_version != self.current_version:
                    self.update_available = True
                    return True, f"发现新版本: {self.latest_version}"
                else:
                    return False, "当前已是最新版本"
            else:
                return False, "无法检查更新"
                
        except Exception as e:
            return False, f"检查更新时出错: {str(e)}"
    
    def download_update(self, progress_callback=None):
        """下载最新版本"""
        try:
            # 获取最新发布版本的下载链接
            url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
            response = requests.get(url, timeout=10)
            release_info = response.json()
            
            # 查找zip格式的发布包
            download_url = None
            for asset in release_info.get('assets', []):
                if asset['name'].endswith('.zip'):
                    download_url = asset['browser_download_url']
                    break
            
            if not download_url:
                # 如果没有预构建的发布包，则下载源代码
                download_url = f"https://github.com/{self.repo_owner}/{self.repo_name}/archive/refs/heads/main.zip"
            
            # 创建临时目录
            temp_dir = Path(tempfile.mkdtemp())
            zip_path = temp_dir / "update.zip"
            
            # 下载文件
            response = requests.get(download_url, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            
            with open(zip_path, 'wb') as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            progress_callback(progress)
            
            return True, temp_dir, zip_path
            
        except Exception as e:
            return False, None, f"下载更新失败: {str(e)}"
    
    def apply_update(self, zip_path, temp_dir):
        """应用更新"""
        try:
            # 解压文件
            extract_dir = temp_dir / "extracted"
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # 找到解压后的主目录
            extracted_folders = list(extract_dir.iterdir())
            if len(extracted_folders) == 1 and extracted_folders[0].is_dir():
                source_dir = extracted_folders[0]
            else:
                source_dir = extract_dir
            
            # 备份当前版本
            backup_dir = self.app_root.parent / f"{self.app_root.name}_backup"
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            shutil.copytree(self.app_root, backup_dir)
            
            # 复制新文件（排除特定文件）
            exclude_files = {'config.json', 'user_settings.ini'}  # 保留用户配置文件
            
            for item in source_dir.iterdir():
                if item.name in exclude_files:
                    continue
                    
                dest_path = self.app_root / item.name
                if item.is_dir():
                    if dest_path.exists():
                        shutil.rmtree(dest_path)
                    shutil.copytree(item, dest_path)
                else:
                    shutil.copy2(item, dest_path)
            
            # 清理临时文件
            shutil.rmtree(temp_dir)
            
            return True, "更新应用成功"
            
        except Exception as e:
            return False, f"应用更新失败: {str(e)}"
    
    def restart_application(self):
        """重启应用程序"""
        try:
            python = sys.executable
            script = sys.argv[0]
            
            # 启动新进程
            subprocess.Popen([python, script])
            
            # 退出当前进程
            dpg.stop_dearpygui()
            
        except Exception as e:
            self.show_error_dialog(f"重启应用程序失败: {str(e)}")
    
    def show_error_dialog(self, message):
        """显示错误对话框"""
        if dpg.does_item_exist("update_error_modal"):
            dpg.delete_item("update_error_modal")
            
        with dpg.window(label="更新错误", modal=True, show=True, tag="update_error_modal", 
                       width=400, height=200):
            dpg.add_text(message)
            dpg.add_button(label="确定", callback=lambda: dpg.delete_item("update_error_modal"))
