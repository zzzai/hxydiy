"""Windows CurrentUser encrypted credentials, enrolled locally without chat or shell secrets."""
import argparse
import ctypes
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from contracts import Stop,require
from runner import save,utc

ORIGIN='https://gray.aizhb.net'
ENTROPY=b'HXY private member collector:gray.aizhb.net:1581452:1581453:v1'

@dataclass(repr=False)
class Credentials:
    account:str
    password:str
    def __repr__(self):return 'Credentials(<redacted>)'


def encode_credentials(value):
    require(type(value.account) is str and 0<len(value.account)<=256 and type(value.password) is str and 0<len(value.password)<=4096,'source_credentials_invalid')
    return json.dumps({'schema':1,'origin':ORIGIN,'tenant_id':1581452,'shop_id':1581453,
                       'account':value.account,'password':value.password},ensure_ascii=False).encode('utf-8')


def decode_credentials(raw):
    try:
        value=json.loads(raw)
        require(set(value)=={'schema','origin','tenant_id','shop_id','account','password'} and
                value['schema']==1 and value['origin']==ORIGIN and value['tenant_id']==1581452 and value['shop_id']==1581453,'source_credentials_scope_invalid')
        result=Credentials(value['account'],value['password']);encode_credentials(result)
        return result
    except Exception:
        raise Stop('source_credentials_invalid') from None


def crypt(raw,decrypt=False):
    require(os.name=='nt' and type(raw) is bytes and 0<len(raw)<=65536,'windows_credentials_required')
    class Blob(ctypes.Structure):
        _fields_=[('size',ctypes.c_uint32),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buf=ctypes.create_string_buffer(raw);entropy=ctypes.create_string_buffer(ENTROPY)
    incoming=Blob(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)))
    binding=Blob(len(ENTROPY),ctypes.cast(entropy,ctypes.POINTER(ctypes.c_ubyte)))
    outgoing=Blob()
    library=ctypes.WinDLL('crypt32',use_last_error=True)
    fn=library.CryptUnprotectData if decrypt else library.CryptProtectData
    fn.restype=ctypes.c_int
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32,ctypes.POINTER(Blob)]
    free=ctypes.WinDLL('kernel32',use_last_error=True).LocalFree
    free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p
    try:
        require(bool(fn(ctypes.byref(incoming),None,ctypes.byref(binding),None,None,1,ctypes.byref(outgoing))),'source_credentials_decryption_failed' if decrypt else 'source_credentials_encryption_failed')
        return ctypes.string_at(outgoing.data,outgoing.size)
    finally:
        ctypes.memset(buf,0,ctypes.sizeof(buf))
        if outgoing.data:
            ctypes.memset(outgoing.data,0,outgoing.size);free(outgoing.data)


def protect(raw):return crypt(raw)
def unprotect(raw):return crypt(raw,True)


def load_credentials(root):
    path=Path(root)/'source-login.dpapi'
    require(path.is_file() and not path.is_symlink() and path.stat().st_size<=65536,'source_credentials_not_configured')
    return decode_credentials(unprotect(path.read_bytes()))


def store_credentials(root,value):
    root=Path(root)
    raw=encode_credentials(value);encrypted=protect(raw)
    require(unprotect(encrypted)==raw,'source_credentials_roundtrip_failed')
    fd,name=tempfile.mkstemp(prefix='.credential-',dir=root)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(encrypted);stream.flush();os.fsync(stream.fileno())
        os.replace(name,root/'source-login.dpapi')
    finally:
        if os.path.exists(name):os.unlink(name)
    save(root/'login-state.json',{'status':'configured','blocked':False,'credential_sha256':hashlib.sha256(encrypted).hexdigest(),'updated_at':utc()})
    save(root/'credential-setup-result.json',{'status':'saved','storage':'Windows CurrentUser DPAPI','origin':ORIGIN,'updated_at':utc()})


def configure(root):
    import tkinter as tk
    from tkinter import ttk
    window=tk.Tk();window.title('智荟宝自动登录 · 本机凭据设置');window.resizable(False,False)
    frame=ttk.Frame(window,padding=24);frame.grid(sticky='nsew')
    ttk.Label(frame,text='录入一次，供后台自动登录',font=('Microsoft YaHei UI',13,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,12))
    ttk.Label(frame,text='仅限 gray.aizhb.net · 荷小悦 / 紫薇壹号店\n账号密码使用 Windows 当前用户加密保存。\n不会写入聊天、Git、日志或上传服务器。',font=('Microsoft YaHei UI',10)).grid(row=1,column=0,columnspan=2,sticky='w',pady=(0,18))
    ttk.Label(frame,text='账号').grid(row=2,column=0,sticky='w',padx=(0,12),pady=8)
    account=ttk.Entry(frame,width=36);account.grid(row=2,column=1,sticky='ew',pady=8)
    ttk.Label(frame,text='密码').grid(row=3,column=0,sticky='w',padx=(0,12),pady=8)
    password=ttk.Entry(frame,width=36,show='*');password.grid(row=3,column=1,sticky='ew',pady=8)
    hint=ttk.Label(frame,text='保存后程序会尝试一次正常登录；验证码需要人工处理。',wraplength=390)
    hint.grid(row=4,column=0,columnspan=2,sticky='w',pady=(12,12))
    def submit():
        try:
            store_credentials(root,Credentials(account.get(),password.get()))
            account.delete(0,tk.END);password.delete(0,tk.END)
            hint.configure(text='已加密保存。正在交回后台程序。');button.state(['disabled'])
            window.after(1000,window.destroy)
        except Exception:
            hint.configure(text='未能保存，请检查账号密码是否已填写。凭据不会输出到日志。')
    def cancel():
        account.delete(0,tk.END);password.delete(0,tk.END)
        save(root/'credential-setup-result.json',{'status':'cancelled','updated_at':utc()});window.destroy()
    button=ttk.Button(frame,text='加密保存',command=submit);button.grid(row=5,column=1,sticky='e')
    ttk.Button(frame,text='取消',command=cancel).grid(row=5,column=0,sticky='w')
    window.protocol('WM_DELETE_WINDOW',cancel);window.mainloop()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--configure',action='store_true',required=True)
    args=parser.parse_args();root=args.root.resolve()
    require(os.name=='nt' and root.is_dir() and not root.is_symlink(),'private_windows_root_required')
    checked=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(Path(__file__).parent/'check-private-root.ps1'),'-PrivateRoot',str(root)],capture_output=True,timeout=15,creationflags=0x08000000)
    require(checked.returncode==0,'private_root_permissions')
    configure(root)

if __name__=='__main__':main()
