import asyncio
import json
import time
import unittest
from aiohttp.test_utils import TestClient, TestServer
from server import make_app

class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app=make_app()
        self.client=TestClient(TestServer(self.app))
        await self.client.start_server()
        response=await self.client.post('/api/rooms',json={'title':'Test session'})
        manager=await response.json()
        self.root='/api/rooms/'+manager['code']
        self.manager={'Authorization':'Bearer '+manager['token']}
        response=await self.client.post(self.root+'/join',json={'name':'Alex'})
        self.player={'Authorization':'Bearer '+(await response.json())['token']}
        self.room=self.app['rooms'][manager['code']]
    async def asyncTearDown(self):
        await self.client.close()
    async def action(self,action,**kwargs):
        return await self.client.post(self.root+'/control',headers=self.manager,json={'action':action,**kwargs})
    async def view(self,headers=None):
        response=await self.client.get(self.root+'/state',headers=headers or self.player)
        return await response.json()
    async def test_authorization_and_results_visibility(self):
        self.assertEqual((await self.client.get(self.root+'/state')).status,401)
        self.assertEqual((await self.client.post(self.root+'/control',headers=self.player,json={'action':'end'})).status,403)
        await self.action('start',scenarioId='investment')
        p=await self.view()
        self.assertNotIn('counts',p['round']);self.assertNotIn('reveal',p['round']);self.assertNotIn('scenarios',p)
        self.assertNotIn(self.room.manager,json.dumps(p))
        response=await self.client.post(self.root+'/vote',headers=self.player,json={'roundId':p['round']['id'],'choice':1})
        self.assertEqual(response.status,200)
        self.assertEqual((await self.view())['round']['myVote'],1)
        self.assertEqual((await self.view(self.manager))['round']['counts'],[0,1,0])
        await self.action('close')
        self.assertNotIn('counts',(await self.view())['round'])
        await self.action('reveal')
        self.assertEqual((await self.view())['round']['counts'],[0,1,0])
        self.assertIn('reveal',(await self.view())['round'])
    async def test_investor_feedback_after_close_reveal_and_timeout(self):
        response=await self.client.post(self.root+'/join',json={'name':'Another investor'})
        other={'Authorization':'Bearer '+(await response.json())['token']}
        for scenario, correct in [('investment',0),('markets',3),('cities',0)]:
            await self.action('start',scenarioId=scenario)
            game=(await self.view())['round']
            self.assertNotIn('correctChoice',game)
            self.assertNotIn('myResult',game)
            await self.client.post(self.root+'/vote',headers=self.player,
                json={'roundId':game['id'],'choice':correct})
            self.assertNotIn('myResult',(await self.view())['round'])
            self.assertNotIn('myResult',(await self.view(other))['round'])
            await self.client.post(self.root+'/vote',headers=other,
                json={'roundId':game['id'],'choice':(correct+1)%len(game['options'])})
            # Expiring the server deadline also makes feedback available before maintenance runs.
            self.room.round['deadline']=time.time()-1
            self.assertEqual((await self.view())['round']['myResult'],'W Investor')
            self.assertEqual((await self.view(other))['round']['myResult'],'L Investory')
            await self.action('close')
            self.assertEqual((await self.view())['round']['myResult'],'W Investor')
            self.assertEqual((await self.view(other))['round']['myResult'],'L Investory')
            self.assertNotIn('counts',(await self.view())['round'])
            self.assertNotIn('myResult',(await self.view(self.manager))['round'])
            await self.action('reveal')
            self.assertEqual((await self.view())['round']['myResult'],'W Investor')
            self.assertEqual((await self.view(other))['round']['myResult'],'L Investory')
            self.assertNotIn('correctChoice',(await self.view())['round'])

    async def test_investor_offer_permissions_feedback_and_replay(self):
        response=await self.client.post(self.root+'/control',headers=self.player,json={'action':'offer','active':True})
        self.assertEqual(response.status,403)
        self.assertEqual((await self.action('offer',active='yes')).status,400)
        await self.action('offer',active=True)
        offer=(await self.view())['offer']
        self.assertTrue(offer['active'])
        self.assertNotIn('counts',offer)
        self.assertEqual((await self.action('start',scenarioId='investment')).status,409)
        self.assertEqual((await self.action('offer',active=True)).status,409)
        for choice,result in [(0,'W Investor'),(1,'L Investor')]:
            response=await self.client.post(self.root+'/vote',headers=self.player,json={'offerId':offer['id'],'choice':choice})
            self.assertEqual(response.status,200)
            self.assertEqual((await self.view())['offer']['myResult'],result)
        self.assertEqual((await self.view(self.manager))['offer']['counts'],[0,1])
        await self.action('panic',active=True)
        response=await self.client.post(self.root+'/vote',headers=self.player,json={'offerId':offer['id'],'choice':0})
        self.assertEqual(response.status,409)
        await self.action('panic',active=False)
        await self.action('offer',active=False)
        response=await self.client.post(self.root+'/vote',headers=self.player,json={'offerId':offer['id'],'choice':0})
        self.assertEqual(response.status,409)
        await self.action('offer',active=True)
        self.assertNotEqual((await self.view())['offer']['id'],offer['id'])
        self.assertEqual((await self.view())['offer']['responses'],0)
        response=await self.client.post(self.root+'/vote',headers=self.player,json={'offerId':offer['id'],'choice':0})
        self.assertEqual(response.status,409)
        await self.action('end')
        self.assertFalse((await self.view())['offer']['active'])

    async def test_deadlines_stale_votes_and_one_vote_per_player(self):
        await self.action('start',scenarioId='investment');rid=self.room.round['id']
        for choice in (0,2):
            response=await self.client.post(self.root+'/vote',headers=self.player,json={'roundId':rid,'choice':choice})
            self.assertEqual(response.status,200)
        self.assertEqual(self.room.counts(),[0,0,1])
        self.room.round['deadline']=time.time()-1
        response=await self.client.post(self.root+'/vote',headers=self.player,json={'roundId':rid,'choice':0})
        self.assertEqual(response.status,409)
        await self.action('reveal');await self.action('start',scenarioId='markets')
        response=await self.client.post(self.root+'/vote',headers=self.player,json={'roundId':rid,'choice':0})
        self.assertEqual(response.status,409)
        response=await self.client.post(self.root+'/vote',headers=self.player,json={'roundId':self.room.round['id'],'choice':True})
        self.assertEqual(response.status,400)
    async def test_captcha_labels_permissions_reveal_and_export(self):
        self.assertEqual((await self.client.post(self.root+'/control', headers=self.player,
            json={'action':'start','scenarioId':'captcha-lab'})).status,403)
        self.assertEqual((await self.action('start',scenarioId='captcha-lab')).status,200)
        game=(await self.view())['round']
        self.assertEqual(game['type'],'captcha')
        self.assertGreaterEqual(game['deadline']-game['openedAt'],59)
        self.assertNotIn('counts',game)
        self.assertNotIn('reveal',game)
        async def submit(tiles, headers=None, rid=None):
            return await self.client.post(self.root+'/vote',headers=headers or self.player,
                json={'roundId':rid or game['id'],'tiles':tiles})
        self.assertEqual((await submit([0],self.manager)).status,403)
        self.assertEqual((await submit([0],rid='stale')).status,409)
        for invalid in (None, '1', [True], [-1], [9], [1,1], [1.5], [{}]):
            self.assertEqual((await submit(invalid)).status,400)
        self.assertEqual((await submit([7,4,3])).status,200)
        self.assertEqual((await self.view())['round']['myVote'],[3,4,7])
        self.assertEqual((await self.view(self.manager))['round']['counts'],[0,0,0,1,1,0,0,1,0])
        # A revision replaces the participant's earlier labels, including all-negative labels.
        self.assertEqual((await submit([])).status,200)
        self.assertEqual((await self.view())['round']['myVote'],[])
        self.assertEqual(self.room.counts(),[0]*9)
        await submit([4,7])
        self.assertEqual((await self.action('start',scenarioId='investment')).status,409)
        self.room.round['deadline']=time.time()-1
        self.assertEqual((await submit([1])).status,409)
        await self.action('close')
        self.assertNotIn('counts',(await self.view())['round'])
        await self.action('reveal')
        result=(await self.view())['round']
        self.assertEqual(result['responses'],1)
        self.assertEqual(result['counts'],[0,0,0,0,1,0,0,1,0])
        self.assertIn('simulation',result['reveal'])
        response=await self.client.get(self.root+'/export',headers=self.manager)
        record=(await response.json())['results'][0]
        self.assertEqual(record['type'],'captcha')
        self.assertEqual(record['counts'],result['counts'])
        self.assertNotIn('votes',record)
        response=await self.client.get('/assets/captcha-cat.jpg')
        self.assertEqual(response.status,200)
        await self.action('start',scenarioId='captcha-lab')
        self.assertIsNone((await self.view())['round']['myVote'])
    async def test_panic_authorization_sync_and_stop(self):
        response=await self.client.post(self.root+'/control',headers=self.player,json={'action':'panic','active':True})
        self.assertEqual(response.status,403)
        self.assertEqual((await self.action('panic',active='yes')).status,400)
        self.assertFalse((await self.view())['panic'])
        self.assertEqual((await self.action('panic',active=True)).status,200)
        self.assertTrue((await self.view())['panic'])
        self.assertTrue((await self.view(self.manager))['panic'])
        self.assertEqual((await self.action('start',scenarioId='investment')).status,409)
        self.assertEqual((await self.action('panic',active=False)).status,200)
        self.assertFalse((await self.view())['panic'])
        self.assertEqual((await self.action('start',scenarioId='investment')).status,200)
        await self.action('panic',active=True)
        await self.action('end')
        self.assertFalse((await self.view())['panic'])
        self.assertEqual((await self.action('panic',active=True)).status,409)
    async def test_panic_blocks_automatic_and_detection_prompts(self):
        self.room.scenarios.append({**self.room.scenarios[0], 'id':'crowd', 'trigger':'crowd'})
        await self.action('settings',automatic=True,visionTriggers=True,interval=15,duration=5)
        await self.action('source',source='demo')
        await self.action('panic',active=True)
        self.room.next_prompt=time.time()-1;self.room.frame_at=time.time()
        await self.action('simulate',people=3);await self.action('simulate',people=3)
        await asyncio.sleep(.65)
        self.assertIsNone(self.room.round)
        await self.action('panic',active=False)
        self.room.next_prompt=time.time()-1
        await asyncio.sleep(.65)
        self.assertEqual(self.room.round['origin'],'timer')
    async def test_face_observations_use_face_counts_and_model_name(self):
        self.room.source='camera';self.room.frame_at=time.time()
        self.room.observe([{'label':'face','score':.95,'box':[.4,.2,.2,.3]}],frame_seq=7)
        obs=(await self.view())['observation']
        self.assertEqual(obs['model'],'OpenCV YuNet')
        self.assertEqual(obs['entity'],'face')
        self.assertEqual(obs['faces'],1)
        self.assertEqual(obs['count'],1)
        self.assertEqual(obs['frameSeq'],7)
        self.assertFalse(obs['simulated'])
        self.assertNotIn('people',obs)
    async def test_settings_and_custom_validation(self):
        self.assertEqual((await self.action('settings',automatic=True,visionTriggers=False,interval=1,duration=10)).status,400)
        data=dict(title='Custom',observation='An event',question='What next?',options=['Wait'],reveal='Discuss')
        self.assertEqual((await self.action('custom',**data)).status,400)
        data['options']=['Wait','Review']
        self.assertEqual((await self.action('custom',**data)).status,200)
        self.assertEqual((await self.action('start',scenarioId=self.room.scenarios[-1]['id'])).status,200)
    async def test_automatic_round_and_reveal(self):
        await self.action('settings',automatic=True,visionTriggers=False,interval=15,duration=5)
        self.room.next_prompt=time.time()-1;await asyncio.sleep(.65)
        self.assertEqual(self.room.round['origin'],'timer')
        self.room.round['deadline']=time.time()-1;await asyncio.sleep(.65)
        self.assertEqual(self.room.round['status'],'closed')
        self.room.round['closedAt']=time.time()-5;await asyncio.sleep(.65)
        self.assertEqual(self.room.round['status'],'revealed');self.assertEqual(len(self.room.history),1)
    async def test_detection_triggers_and_simulation_label(self):
        self.room.scenarios.append({**self.room.scenarios[0], 'id': 'crowd', 'trigger': 'crowd'})
        await self.action('settings',automatic=False,visionTriggers=True,interval=15,duration=5)
        await self.action('source',source='demo');self.room.frame_at=time.time();await self.action('simulate',people=3)
        self.assertIsNone(self.room.round)
        await self.action('simulate',people=3)
        self.assertEqual(self.room.round['scenarioId'],'crowd')
        self.assertEqual(self.room.round['origin'],'simulated detection')
        self.assertTrue(self.room.round['evidence']['simulated'])
        rid=self.room.round['id'];await self.action('reveal');await self.action('simulate',people=3)
        self.assertEqual(self.room.round['id'],rid)
    async def test_detection_without_matching_scenario(self):
        await self.action('settings',automatic=False,visionTriggers=True,interval=15,duration=5)
        await self.action('source',source='demo');self.room.frame_at=time.time()
        for people in (1,1,3,3):
            self.assertEqual((await self.action('simulate',people=people)).status,200)
        self.assertIsNone(self.room.round)
    async def test_stale_feed_does_not_trigger_round(self):
        await self.action('settings',automatic=False,visionTriggers=True,interval=15,duration=5)
        await self.action('source',source='demo')
        await self.action('simulate',people=3);await self.action('simulate',people=3)
        self.assertIsNone(self.room.round)
    async def test_ending_clears_frames_and_blocks_mutations(self):
        await self.action('source',source='demo');self.room.frame=b'frame'
        await self.action('start',scenarioId='investment');await self.action('end')
        self.assertIsNone(self.room.frame);self.assertTrue((await self.view())['ended'])
        self.assertEqual((await self.view())['round']['status'],'revealed')
        self.assertEqual((await self.client.post(self.root+'/join',json={'name':'Late'})).status,409)
        self.assertEqual((await self.action('start',scenarioId='markets')).status,409)
        self.assertEqual((await self.client.get(self.root+'/frame',headers=self.player)).status,204)
    async def test_frame_authorization_and_expiration(self):
        await self.action('source',source='camera');jpeg=b'\xff\xd8'+b'x'*150+b'\xff\xd9'
        self.assertEqual((await self.client.post(self.root+'/frame',headers={**self.player,'Content-Type':'image/jpeg'},data=jpeg)).status,403)
        self.assertEqual((await self.client.post(self.root+'/frame',headers={**self.manager,'Content-Type':'image/jpeg'},data=jpeg)).status,200)
        self.assertEqual(await (await self.client.get(self.root+'/frame',headers=self.player)).read(),jpeg)
        self.room.frame_at=time.time()-4
        self.assertEqual((await self.client.get(self.root+'/frame',headers=self.player)).status,204)
    async def test_export_has_no_credentials(self):
        await self.action('start',scenarioId='investment');await self.action('reveal')
        self.assertEqual((await self.client.get(self.root+'/export',headers=self.player)).status,403)
        response=await self.client.get(self.root+'/export',headers=self.manager);exported=await response.text()
        self.assertNotIn(self.manager['Authorization'][7:],exported);self.assertNotIn(self.player['Authorization'][7:],exported)
        self.assertEqual(len(json.loads(exported)['results']),1)
    async def test_sse_streams_authenticated_state(self):
        response=await self.client.get(self.root+'/events',headers=self.player)
        line=await asyncio.wait_for(response.content.readline(),2);self.assertTrue(line.startswith(b'data: '))
        data=json.loads(line[6:]);self.assertEqual(data['online'],1);self.assertNotIn('scenarios',data);response.close()
    async def test_cross_origin_mutations_rejected(self):
        response=await self.client.post(self.root+'/control',headers={**self.manager,'Origin':'https://other.example'},json={'action':'end'})
        self.assertEqual(response.status,403);self.assertFalse(self.room.ended)

if __name__=='__main__':unittest.main()
