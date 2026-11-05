from starlette.responses import JSONResponse
class LocalGuard:
    def __init__(self, app, token): self.app=app; self.token=token
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http': return await self.app(scope,receive,send)
        headers=dict(scope.get('headers',[])); host=headers.get(b'host',b'').decode().split(':')[0]
        if host not in ('127.0.0.1','localhost'):
            return await JSONResponse({'error':'Invalid host'},status_code=400)(scope,receive,send)
        if scope['method'] not in ('GET','HEAD') and headers.get(b'x-offerletter-token',b'').decode()!=self.token:
            return await JSONResponse({'error':'Invalid request token'},status_code=403)(scope,receive,send)
        return await self.app(scope,receive,send)


