from __future__ import annotations
import math, struct
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from .features import FeaturePlan, dynamic_chain
from .obj import Material, ObjMesh
from .rig import Bone
from .weights import VertexWeight, compute_group_vertex_weights, summarize_weights, weights_for_layered_point

def _text(v:str)->bytes:
    raw=v.encode('utf-16-le'); return struct.pack('<i',len(raw))+raw
def _vec2(v): return struct.pack('<2f',*v)
def _vec3(v): return struct.pack('<3f',*v)
def _vec4(v): return struct.pack('<4f',*v)
def _mmd_vec3(v): return (v[0],v[1],-v[2])
def _mmd_uv(v,*,flip_u=False):
    u,w=v; return (1-u if flip_u else u,1-w)
def _planar_uv_flip_groups(mesh,threshold=.025):
    out=set()
    for group,indices in mesh.group_vertex_indices().items():
        if not group.lower().startswith('handle') or not indices: continue
        lo,hi=mesh.bounds(indices); size=tuple(max(float(hi[i]-lo[i]),0) for i in range(3)); longest=max(size)
        if longest>1e-8 and min(size)/longest<=threshold: out.add(group)
    return out
MMD_JP={'center':'センター','hips':'下半身','spine':'上半身','chest':'上半身2','neck':'首','head':'頭','eyes':'両目','leftEye':'左目','rightEye':'右目','leftUpperArm':'左腕','leftLowerArm':'左ひじ','leftHand':'左手首','rightUpperArm':'右腕','rightLowerArm':'右ひじ','rightHand':'右手首','leftUpperLeg':'左足','leftLowerLeg':'左ひざ','leftFoot':'左足首','rightUpperLeg':'右足','rightLowerLeg':'右ひざ','rightFoot':'右足首','leftLegIK':'左足ＩＫ','rightLegIK':'右足ＩＫ'}
@dataclass(frozen=True)
class _PmxBone:
    name:str; parent:str|None; position:tuple[float,float,float]; ik_target:str|None=None; ik_links:tuple[str,...]=()
@dataclass(frozen=True)
class _BoneMorph:
    name_jp:str; name_en:str; bone_name:str; rotation:tuple[float,float,float,float]
@dataclass(frozen=True)
class _VertexMorph:
    name_jp:str; name_en:str; panel:int; offsets:list[tuple[int,tuple[float,float,float]]]
@dataclass(frozen=True)
class _RigidBody:
    name:str; bone_name:str; shape_size:tuple[float,float,float]; position:tuple[float,float,float]; operation:int; mass:float; linear_damping:float; angular_damping:float; group:int; collision_mask:int
@dataclass(frozen=True)
class _Joint:
    name:str; rigid_a:str; rigid_b:str; position:tuple[float,float,float]; angular_limit:float; spring:float

def _quat_axis_angle(axis,angle):
    h=angle/2;s=math.sin(h);return (axis[0]*s,axis[1]*s,axis[2]*s,math.cos(h))
def _pmx_bones(bones,features):
    by={b.name:b for b in bones}; hips=by.get('hips') or bones[0]; result=[_PmxBone('center',None,hips.position)]
    for b in bones: result.append(_PmxBone(b.name,'center' if b.name=='hips' else b.parent,b.position))
    if features and features.eyes:
        e=features.eyes; result += [_PmxBone('eyes','head',e.master_position),_PmxBone('leftEye','eyes',e.left_position),_PmxBone('rightEye','eyes',e.right_position)]
    if features:
        for d in features.dynamics:
            for s in dynamic_chain(d): result.append(_PmxBone(s['name'],s['parent'],tuple(s['position'])))
    for side in ('left','right'):
        foot,lower,upper=f'{side}Foot',f'{side}LowerLeg',f'{side}UpperLeg'
        if foot in by and lower in by and upper in by: result.append(_PmxBone(f'{side}LegIK','center',by[foot].position,foot,(lower,upper)))
    return result
def _eye_morphs(features):
    if not features or not features.eyes:return []
    yaw=math.radians(18);pitch=math.radians(12)
    return [_BoneMorph('視線左','LookLeft','eyes',_quat_axis_angle((0,1,0),yaw)),_BoneMorph('視線右','LookRight','eyes',_quat_axis_angle((0,1,0),-yaw)),_BoneMorph('視線上','LookUp','eyes',_quat_axis_angle((1,0,0),-pitch)),_BoneMorph('視線下','LookDown','eyes',_quat_axis_angle((1,0,0),pitch))]
def _group_components(mesh: ObjMesh, group: str):
    faces=[face for face in mesh.faces if face.group==group]
    adj=defaultdict(set); vertices=set()
    for face in faces:
        ids=[c[0] for c in face.corners]; vertices.update(ids)
        for i in range(len(ids)):
            for j in range(i+1,len(ids)):
                adj[ids[i]].add(ids[j]); adj[ids[j]].add(ids[i])
    seen=set(); comps=[]
    for start in vertices:
        if start in seen: continue
        stack=[start]; seen.add(start); comp=set()
        while stack:
            v=stack.pop(); comp.add(v)
            for n in adj[v]:
                if n not in seen: seen.add(n); stack.append(n)
        comps.append(comp)
    return comps

def _reconstructed_face_morphs(mesh: ObjMesh, group_to_bone, source_to_pmx) -> list[_VertexMorph]:
    groups=mesh.group_vertex_indices()
    candidates=[g for g in groups if group_to_bone.get(g)=='head' and g.lower().startswith('rig')]
    if not candidates: candidates=[g for g in groups if group_to_bone.get(g)=='head']
    if not candidates: return []
    group=max(candidates,key=lambda g: len(groups[g]))
    indices=groups[group]
    lo,hi=mesh.bounds(indices); center=tuple((lo[i]+hi[i])*0.5 for i in range(3)); size=tuple(max(hi[i]-lo[i],1e-6) for i in range(3)); w,h,d=size
    front_cut=lo[2]+0.25*d
    comp_stats=[]
    for comp in _group_components(mesh,group):
        pts=[mesh.vertices[i] for i in comp]
        clo=tuple(min(p[a] for p in pts) for a in range(3)); chi=tuple(max(p[a] for p in pts) for a in range(3))
        cc=tuple((clo[a]+chi[a])*0.5 for a in range(3)); cs=tuple(chi[a]-clo[a] for a in range(3))
        comp_stats.append((comp,cc,cs))
    eye=[]; mouth=[]
    for comp,cc,cs in comp_stats:
        ax=abs(cc[0]-center[0])
        if cc[2] <= front_cut and 0.08*w <= ax <= 0.44*w and center[1]-0.20*h <= cc[1] <= center[1]+0.06*h and cs[0] <= 0.40*w and cs[1] <= 0.34*h:
            eye.append((comp,cc,cs))
        if cc[2] <= front_cut and ax <= 0.21*w and center[1]-0.43*h <= cc[1] <= center[1]-0.24*h and cs[0] <= 0.32*w and cs[1] <= 0.22*h:
            mouth.append((comp,cc,cs))
    left_src=set().union(*(c for c,cc,cs in eye if cc[0]>=center[0])) if eye else set()
    right_src=set().union(*(c for c,cc,cs in eye if cc[0]<center[0])) if eye else set()
    mouth_src=set().union(*(c for c,cc,cs in mouth)) if mouth else set()
    morphs=[]
    def blink(name_jp,name_en,src):
        if len(src)<12:return None
        ys=[mesh.vertices[i][1] for i in src]; line=sum(ys)/len(ys)
        offsets=[]
        for vi in src:
            p=mesh.vertices[vi]; delta=(0.0,(line-p[1])*0.88,0.0)
            if abs(delta[1])<1e-5: continue
            for pi in source_to_pmx.get((group,vi),()): offsets.append((pi,_mmd_vec3(delta)))
        return _VertexMorph(name_jp,name_en,2,offsets) if offsets else None
    lb=blink('ウィンク','BlinkLeft',left_src); rb=blink('ウィンク右','BlinkRight',right_src)
    if lb and rb:
        morphs.append(_VertexMorph('まばたき','Blink',2,lb.offsets+rb.offsets)); morphs.extend([lb,rb])
    elif lb:morphs.append(lb)
    elif rb:morphs.append(rb)
    if len(mouth_src)>=12:
        ys=[mesh.vertices[i][1] for i in mouth_src]; line=sum(ys)/len(ys); open_offsets=[]; smile_offsets=[]
        for vi in mouth_src:
            p=mesh.vertices[vi]; rel_y=p[1]-line; rel_x=p[0]-center[0]
            dy_open=(-0.075*h if rel_y<=0 else 0.018*h) * (0.55+0.45*min(abs(rel_y)/(0.11*h),1.0))
            xnorm=min(abs(rel_x)/(0.21*w),1.0); dy_smile=0.045*h*(xnorm**1.25); dx_smile=(0.015*w*xnorm)*(1 if rel_x>=0 else -1)
            for pi in source_to_pmx.get((group,vi),()):
                open_offsets.append((pi,_mmd_vec3((0.0,dy_open,0.0))))
                smile_offsets.append((pi,_mmd_vec3((dx_smile,dy_smile,0.0))))
        if open_offsets:morphs.append(_VertexMorph('あ','MouthOpen',3,open_offsets))
        if smile_offsets:morphs.append(_VertexMorph('笑い','Smile',3,smile_offsets))
    return morphs

def _chain_vertex_weights(point,dynamic):
    chain=dynamic_chain(dynamic)
    if not chain:return []
    if len(chain)==1:return [VertexWeight(chain[0]['name'],1)]
    root=dynamic.root_position; tail=dynamic.tail_position; axis=tuple(tail[i]-root[i] for i in range(3)); denom=sum(v*v for v in axis)
    if denom<=1e-12:return [VertexWeight(chain[0]['name'],1)]
    rel=tuple(point[i]-root[i] for i in range(3)); t=max(0,min(1,sum(rel[i]*axis[i] for i in range(3))/denom)); scaled=t*(len(chain)-1); left=min(int(scaled),len(chain)-1); right=min(left+1,len(chain)-1)
    if left==right:return [VertexWeight(chain[left]['name'],1)]
    blend=scaled-left; return [VertexWeight(chain[left]['name'],1-blend),VertexWeight(chain[right]['name'],blend)]
def _physics(features,bones):
    if not features:return [],[]
    bonepos={b.name:b.position for b in bones}; rigid=[]; joints=[]; anchors={}
    for d in features.dynamics:
        chain=dynamic_chain(d)
        if not chain: continue
        parent=d.parent_bone
        if parent not in anchors:
            name=f'rackAnchor_{parent}';anchors[parent]=name;rigid.append(_RigidBody(name,parent,(.04,.04,.04),bonepos.get(parent,d.root_position),0,0,1,1,0,0xFFFF))
        prev=anchors[parent]; sc=max(len(chain),1)
        for idx,s in enumerate(chain):
            body=f'rackBody_{d.group}_{idx+1:02d}'; half=tuple(max(min(float(v)*.12/sc,.22),.025) for v in d.size); volume=max(d.size[0]*d.size[1]*d.size[2],.001); mass=max(.03,min(volume*.025/sc,.35))
            rigid.append(_RigidBody(body,s['name'],half,tuple(s['position']),1,mass,max(d.drag_force,.65),max(min(d.drag_force+.2,.95),.75),1,0xFFFF))
            joints.append(_Joint(f'rackJoint_{d.group}_{idx+1:02d}',prev,body,tuple(s['position']),min(d.angular_limit*.45,.28),12+30*d.stiffness));prev=body
    return rigid,joints
def _write_weight(blob,bone_index,values):
    vals=[v for v in values if v.bone in bone_index]
    if len(vals)<=1:
        bone=bone_index.get(vals[0].bone if vals else 'spine',0); blob += struct.pack('<Bi',0,bone)
    elif len(vals)==2:
        a,b=vals; blob += struct.pack('<Bii',1,bone_index[a.bone],bone_index[b.bone])+struct.pack('<f',a.weight)
    else:
        vals=vals[:4]
        while len(vals)<4: vals.append(VertexWeight(vals[0].bone,0))
        total=sum(v.weight for v in vals) or 1; blob+=struct.pack('<B',2)
        for v in vals: blob+=struct.pack('<i',bone_index[v.bone])
        for v in vals: blob+=struct.pack('<f',v.weight/total)
    return blob

def write_pmx(output:Path,*,model_name:str,mesh:ObjMesh,materials:dict[str,Material],bones:list[Bone],group_to_bone:dict[str,str],smooth_weights=True,features:FeaturePlan|None=None,accessory_physics=True):
    pmx_bones=_pmx_bones(bones,features); bone_index={b.name:i for i,b in enumerate(pmx_bones)}; mapping=dict(group_to_bone)
    spring={d.group:d for d in (features.dynamics if features and accessory_physics else ()) if d.physics_mode=='spring'}; planar=_planar_uv_flip_groups(mesh)
    textures=[]
    for m in materials.values():
        if m.map_kd and m.map_kd not in textures:textures.append(m.map_kd)
    texidx={n:i for i,n in enumerate(textures)}
    weights=compute_group_vertex_weights(mesh,bones,mapping,smooth=smooth_weights)
    layered={x.group:x for x in (features.layered_clothing if features else ())}; layered_groups=set(layered)
    for group,item in layered.items():
        for i in mesh.group_vertex_indices().get(group,()): weights[(group,i)]=weights_for_layered_point(mesh.vertices[i],bones,profile=item.profile)
    for group,d in spring.items():
        for i in mesh.group_vertex_indices().get(group,()): weights[(group,i)]=_chain_vertex_weights(mesh.vertices[i],d)
    vertex_map={};out_vertices=[]; source_to_pmx=defaultdict(list); indices_by_material=defaultdict(list)
    for face in mesh.faces:
        fi=[]
        for vi,ui,ni in face.corners:
            key=(vi,ui,ni,face.group)
            if key not in vertex_map:
                pos=_mmd_vec3(mesh.vertices[vi]); uv=_mmd_uv(mesh.uvs[ui],flip_u=face.group in planar) if ui is not None and 0<=ui<len(mesh.uvs) else (0,0); normal=_mmd_vec3(mesh.normals[ni]) if ni is not None and 0<=ni<len(mesh.normals) else (0,1,0); w=weights.get((face.group,vi)) or []
                vertex_map[key]=len(out_vertices); out_vertices.append((pos,normal,uv,w)); source_to_pmx[(face.group,vi)].append(vertex_map[key])
            fi.append(vertex_map[key])
        indices_by_material[face.material].extend(reversed(fi))
    material_order=list(dict.fromkeys(f.material for f in mesh.faces)); vertex_morphs=_reconstructed_face_morphs(mesh,mapping,source_to_pmx); bone_morphs=_eye_morphs(features); morphs=vertex_morphs+bone_morphs; rigid,joints=_physics(features if accessory_physics else None,pmx_bones); ridx={b.name:i for i,b in enumerate(rigid)}
    blob=bytearray(b'PMX ');blob+=struct.pack('<fB',2.0,8)+bytes([0,0,4,4,4,4,4,4]);comment='Generated by Roblox Avatar Conversion Kit v0.3.9. Skin weights and accessory physics are reconstructed and approximate.';blob+=_text(model_name)+_text(model_name)+_text(comment)+_text(comment)
    blob+=struct.pack('<i',len(out_vertices));counts=defaultdict(int)
    for pos,n,uv,w in out_vertices:
        blob+=_vec3(pos)+_vec3(n)+_vec2(uv);blob=_write_weight(blob,bone_index,w);counts[min(max(len(w),1),4)]+=1;blob+=struct.pack('<f',1.0)
    flat=[i for m in material_order for i in indices_by_material[m]];blob+=struct.pack('<i',len(flat));
    for i in flat:blob+=struct.pack('<I',i)
    blob+=struct.pack('<i',len(textures));
    for t in textures:blob+=_text(t)
    blob+=struct.pack('<i',len(material_order))
    for num,mname in enumerate(material_order):
        m=materials.get(mname or '') or Material(mname or f'Material{num+1}');blob+=_text(m.name)+_text(m.name)+_vec4((*m.kd,m.alpha))+_vec3(m.ks)+struct.pack('<f',max(0,m.ns))+_vec3(tuple(c*.35 for c in m.kd))+struct.pack('<B',0x0F)+_vec4((0,0,0,1))+struct.pack('<f',0)+struct.pack('<iiBBB',texidx.get(m.map_kd,-1),-1,0,1,0)+_text('')+struct.pack('<i',len(indices_by_material[mname]))
    blob+=struct.pack('<i',len(pmx_bones))
    for b in pmx_bones:
        parent=bone_index.get(b.parent,-1) if b.parent else -1;blob+=_text(MMD_JP.get(b.name,b.name))+_text(b.name)+_vec3(_mmd_vec3(b.position))+struct.pack('<ii',parent,0);flags=0x001A
        if b.name=='center':flags|=0x0004
        if b.ik_target:flags|=0x0020|0x0004
        blob+=struct.pack('<H',flags)+_vec3((0,.1,0))
        if b.ik_target:
            blob+=struct.pack('<iif',bone_index[b.ik_target],40,.5)+struct.pack('<i',len(b.ik_links))
            for link in b.ik_links:blob+=struct.pack('<iB',bone_index[link],0)
    blob+=struct.pack('<i',len(morphs))
    for m in morphs:
        if isinstance(m,_VertexMorph):
            blob+=_text(m.name_jp)+_text(m.name_en)+struct.pack('<BBi',m.panel,1,len(m.offsets))
            for vertex_index,delta in m.offsets: blob+=struct.pack('<I',vertex_index)+_vec3(delta)
        else:
            blob+=_text(m.name_jp)+_text(m.name_en)+struct.pack('<BBi',2,2,1)+struct.pack('<i',bone_index[m.bone_name])+_vec3((0,0,0))+_vec4(m.rotation)
    frames=[('Root','Root',1,[(0,bone_index['center'])])]
    if morphs:frames.append(('表情','Expressions',1,[(1,i) for i in range(len(morphs))]))
    facebones=[n for n in ('head','eyes','leftEye','rightEye') if n in bone_index]
    if facebones:frames.append(('顔','Face',0,[(0,bone_index[n]) for n in facebones]))
    physics_bones=[s['name'] for d in (features.dynamics if features and accessory_physics else ()) for s in dynamic_chain(d) if s['name'] in bone_index]
    if physics_bones:frames.append(('物理','Physics',0,[(0,bone_index[n]) for n in physics_bones]))
    blob+=struct.pack('<i',len(frames))
    for local,en,special,elements in frames:
        blob+=_text(local)+_text(en)+struct.pack('<Bi',special,len(elements))
        for typ,idx in elements:blob+=struct.pack('<Bi',typ,idx)
    blob+=struct.pack('<i',len(rigid))
    for b in rigid:
        blob+=_text(b.name)+_text(b.name)+struct.pack('<iBH',bone_index.get(b.bone_name,-1),b.group,b.collision_mask)+struct.pack('<B',1)+_vec3(b.shape_size)+_vec3(_mmd_vec3(b.position))+_vec3((0,0,0))+struct.pack('<fffffB',b.mass,b.linear_damping,b.angular_damping,0,.5,b.operation)
    blob+=struct.pack('<i',len(joints))
    for j in joints:
        lim=j.angular_limit;blob+=_text(j.name)+_text(j.name)+struct.pack('<Bii',0,ridx[j.rigid_a],ridx[j.rigid_b])+_vec3(_mmd_vec3(j.position))+_vec3((0,0,0))+_vec3((0,0,0))+_vec3((0,0,0))+_vec3((-lim,-lim*.55,-lim))+_vec3((lim,lim*.55,lim))+_vec3((0,0,0))+_vec3((j.spring,j.spring*.6,j.spring))
    Path(output).write_bytes(blob)
    return {'vertices':len(out_vertices),'triangles':len(flat)//3,'materials':len(material_order),'textures':len(textures),'bones':len(pmx_bones),'ik_bones':sum(1 for b in pmx_bones if b.ik_target),'gaze_morphs':len(bone_morphs),'reconstructed_face_morphs':len(vertex_morphs),'face_morph_group':max((g for g in mesh.group_vertex_indices() if mapping.get(g)=='head' and g.lower().startswith('rig')),key=lambda g: len(mesh.group_vertex_indices()[g]),default=None),'dynamic_accessory_bones':len(physics_bones),'rigid_bodies':len(rigid),'physics_joints':len(joints),'spring_accessories':len(spring),'layered_clothing_groups':len(layered_groups),'planar_uv_flip_groups':len(planar),'weight_modes':dict(sorted(counts.items())),'source_weight_summary':summarize_weights(weights),'text_encoding':'utf-16-le','bytes':len(blob)}
