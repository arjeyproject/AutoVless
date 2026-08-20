import json, aiohttp, os
from config import logger

class CloudflareAPI:
    def __init__(self, token):
        self.token = token
        self.base = "https://api.cloudflare.com/client/v4"
    
    async def call(self, method, endpoint, data=None):
        headers = {'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}
        async with aiohttp.ClientSession() as s:
            async with s.request(method, f"{self.base}{endpoint}", json=data, headers=headers) as r:
                res = await r.json()
                if not res.get('success'):
                    raise Exception(res['errors'][0]['message'] if res.get('errors') else 'API Error')
                return res.get('result', res)
    
    async def get_account_id(self):
        accs = await self.call('GET', '/accounts')
        return accs[0]['id']
    
    async def create_kv_namespace(self, account_id, name):
        res = await self.call('POST', f'/accounts/{account_id}/storage/kv/namespaces', {'title': name})
        return res['id']
    
    async def update_kv_value(self, account_id, ns_id, key, value):
        await self.call('PUT', f'/accounts/{account_id}/storage/kv/namespaces/{ns_id}/values/{key}', {'value': json.dumps(value)})
    
    async def deploy_worker(self, account_id, worker_name, code):
        await self.call('PUT', f'/accounts/{account_id}/workers/scripts/{worker_name}', {
            'main': {'name': 'index', 'type': 'esm', 'content': code}
        })
        return f'{worker_name}.nova-564b13.workers.dev'
    
    async def bind_kv_to_worker(self, account_id, worker_name, ns_id):
        await self.call('PUT', f'/accounts/{account_id}/workers/scripts/{worker_name}/settings', {
            'bindings': [{'name': 'AUTOVLESS_KV', 'type': 'kv_namespace', 'namespace_id': ns_id}]
        })

async def setup_user(user_id, cf_token):
    try:
        cf = CloudflareAPI(cf_token)
        account_id = await cf.get_account_id()
        ns_id = await cf.create_kv_namespace(account_id, f'autovless_{user_id}')
        
        with open('/app/worker/vless-worker.js', 'r') as f:
            worker_code = f.read()
        
        worker_name = f'vless-{user_id}'
        worker_url = await cf.deploy_worker(account_id, worker_name, worker_code)
        await cf.bind_kv_to_worker(account_id, worker_name, ns_id)
        
        return {'success': True, 'account_id': account_id, 'ns_id': ns_id, 'worker_url': worker_url, 'worker_name': worker_name}
    except Exception as e:
        return {'success': False, 'error': str(e)}

async def store_ips(account_id, ns_id, ips, cf_token):
    try:
        cf = CloudflareAPI(cf_token)
        await cf.update_kv_value(account_id, ns_id, 'ips', ips)
        return True
    except Exception as e:
        logger.error(f"KV store failed: {e}")
        return False
