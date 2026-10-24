import importlib.util, json, math
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('driver',root/'scripts/drive_to_goal_v4.py')
driver=importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
def scan_at(pose,box):
    x,y,yaw=pose
    origin=(x+.12*math.cos(yaw),y+.12*math.sin(yaw))
    ranges=[]
    for i in range(180):
        a=-math.pi+i*2*math.pi/179
        direction=(math.cos(yaw+a),math.sin(yaw+a))
        lo,hi=0.,8.
        if box is None:
            ranges.append(math.inf)
            continue
        for o,d,lower,upper in zip(origin,direction,box[:2],box[2:]):
            if abs(d)<1e-10:
                if not lower<=o<=upper: hi=-1
            else:
                t1,t2=sorted(((lower-o)/d,(upper-o)/d))
                lo,hi=max(lo,t1),min(hi,t2)
        ranges.append(lo if .05<=lo<=hi else math.inf)
    return SimpleNamespace(ranges=ranges,angle_min=-math.pi,angle_increment=2*math.pi/179,range_min=.05,range_max=8.)
def trial(name,box,delay_steps=0):
    planner=driver.LidarPlanner()
    pose=(0.,0.,0.)
    minimum,avoids=100.,0
    scan_history=[]
    for step in range(2400):
        scan_history.append(scan_at(pose,box))
        delayed_scan=scan_history[max(0,len(scan_history)-1-delay_steps)]
        v,w,state,clearance=planner.command(pose,delayed_scan)
        if state=='GOAL':
            return dict(name=name,result='PASS',seconds=step*.1,final_pose=pose,avoid_steps=avoids,min_circumscribed_margin=minimum if box else None)
        assert state not in ('BLOCKED','INVALID_SCAN'),(name,pose,state)
        avoids+=state=='AVOID'
        x,y,yaw=pose
        pose=(x+.1*v*math.cos(yaw+.05*w),y+.1*v*math.sin(yaw+.05*w),driver.wrap(yaw+.1*w))
        if box:
            dx=max(box[0]-pose[0],0.,pose[0]-box[2])
            dy=max(box[1]-pose[1],0.,pose[1]-box[3])
            margin=math.hypot(dx,dy)-.33
            minimum=min(minimum,margin)
            assert margin>0,(name,'synthetic collision',pose)
    raise AssertionError((name,'timeout',pose))
results=[trial('empty',None),trial('path_obstacle',(1.25,.15,1.75,.85)),trial('original_obstacle',(1.75,-.35,2.25,.35))]
results += [trial('path_obstacle_scan_delay_100ms',(1.25,.15,1.75,.85),1), trial('path_obstacle_scan_delay_300ms',(1.25,.15,1.75,.85),3)]
p=driver.LidarPlanner()
s=scan_at((0,0,0),None)
for value in (math.nan,-math.inf,0.):
    s.ranges[90]=value
    assert p.command((0,0,0),s)[2]=='INVALID_SCAN'
s.ranges=[.2]*180
assert p.command((0,0,0),s)[2]=='BLOCKED'
s.ranges=[]
assert p.command((0,0,0),s)[2]=='INVALID_SCAN'
for f in (root/'scripts').glob('*.py'): compile(f.read_text(encoding='utf-8-sig'),str(f),'exec')
world=ET.parse(root/'simulation/worlds/practice.sdf')
assert world.find(".//model[@name='obstacle']/pose").text=='1.5 0.5 0.4 0 0 0'
robot=world.find(".//model[@name='practice_robot']")
assert robot.find("link[@name='front_caster']/pose").text=='0.20 0 0.05 0 0 0'
assert robot.find("joint[@name='front_caster_joint']/child").text=='front_caster'
assert world.find(".//sensor[@name='obstacle_contact']/contact/topic").text=='/step2/obstacle_contacts'
assert world.find(".//sensor[@name='attitude']") is not None
for case in results:
    assert math.hypot(3-case['final_pose'][0], 1-case['final_pose'][1]) < .03
# A bound from the measured v3 run, not a new physical-world measurement.
measured_drift_bound=.178143970581869
assert measured_drift_bound+.03 < .25
report=dict(test_type='V4 OFFLINE SYNTHETIC ONLY; NOT GAZEBO/ROS',cases=results,invalid_scan_and_blocked='PASS',python_syntax='PASS',sdf_xml_front_support_and_sensors='PASS')
(root/'outputs/step2-v4-offline-tests.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
