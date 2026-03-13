from pyrogram import Client


def register_all(app: Client):
    from handlers.admin    import register as reg_admin
    from handlers.upload   import register as reg_upload
    from handlers.settings import register as reg_settings

    reg_admin(app)
    reg_upload(app)
    reg_settings(app)
