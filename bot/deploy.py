import json, aiohttp
from config import logger

class CloudflareDeployer:
    def __init__(self, api_token):
        self.api_token = api_token
        self.base_url = "https://api.cloudflare.com/client/v4"
    
    async def request(self, method, endpoint, data=None):
        headers = {'Authorization': f'Bearer {self.api_token}', 'Content-Type': 'application/json'}
        async with aiohttp.ClientSession() as session:
            async with session.request(method, f"{self.base_url}{endpoint}", json=data, headers=headers) as resp:
                result = await resp.json()
                if not result.get('success'):
                    raise Exception(result.get('errors', [{}])[0].get('message'))
                return result.get('result', result)
    
    async def get_account_id(self):
        accs = await self.request('GET', '/accounts')
        return accs[0]['id'] if isinstance(accs, list) else accs['id']
    
    async def create_kv_namespace(self, account_id, name):
        res = await self.request('POST', f'/accounts/{account_id}/storage/kv/namespaces', {'title': name})
        return res['id']
    
    async def deploy_worker(self, account_id, worker_name, code, ns_id):
        await self.request('PUT', f'/accounts/{account_id}/workers/scripts/{worker_name}', 
            {'main': {'name': 'index', 'type': 'esm', 'content': code}})
        await self.request('PUT', f'/accounts/{account_id}/workers/scripts/{worker_name}/bindings',
            {'bindings': [{'name': 'AUTOVLESS_KV', 'type': 'kv_namespace', 'namespace_id': ns_id}]})
        return f'{worker_name}.workers.dev'
    
    async def put_kv_ips(self, account_id, ns_id, ips):
        await self.request('PUT', f'/accounts/{account_id}/storage/kv/namespaces/{ns_id}/values/ips',
            {'value': json.dumps(ips)})
