"""Route argument edges around nodes; share the same geometry across options."""
import json
import shutil
import subprocess


def layout(figures):
    binary=shutil.which('dot')
    if not binary: raise ValueError('논증 도식에는 Graphviz가 필요합니다: macOS brew install graphviz / Linux apt install graphviz')
    labels={n.id:n.label for n in figures[0].nodes}
    if any({n.id:n.label for n in f.nodes} != labels for f in figures):
        raise ValueError('논증 선택지의 노드 ID·표시가 다릅니다')
    nodes={key:f'n{i}' for i,key in enumerate(labels)}
    joint_keys=sorted({(tuple(sorted(e.sources)),e.target,e.relation)
                       for f in figures for e in f.edges if len(e.sources)>1})
    joints={key:f'j{i}' for i,key in enumerate(joint_keys)}
    segments={};active={};active_joints={}
    for f in figures:
        selected=[];dots=[]
        for e in f.edges:
            start=nodes[e.sources[0]]
            if len(e.sources)>1:
                start=joints[(tuple(sorted(e.sources)),e.target,e.relation)];dots.append(start)
                for s in e.sources:
                    key=(nodes[s],start,'none')
                    segments.setdefault(key,f'e{len(segments)}');selected.append(segments[key])
            key=(start,nodes[e.target],'normal' if e.relation=='support' else 'tee')
            segments.setdefault(key,f'e{len(segments)}');selected.append(segments[key])
        active[f.id]=selected;active_joints[f.id]=dots
    lines=['digraph G {','graph [rankdir=TB,nodesep=.12,ranksep=.20,splines=true,outputorder=edgesfirst];',
           'node [label="",shape=circle,width=.42,height=.42,fixedsize=true];']
    lines += [f'{node};' for node in nodes.values()]
    lines += [f'{node} [shape=point,width=.045,height=.045];' for node in joints.values()]
    lines += [f'{s} -> {t} [id="{eid}",arrowhead={arrow},style={"dashed" if arrow=="tee" else "solid"}];'
              for (s,t,arrow),eid in segments.items()]
    lines.append('}')
    result=subprocess.run([binary,'-Tjson'],input='\n'.join(lines),text=True,capture_output=True,timeout=30)
    if result.returncode:raise ValueError('논증 배치 실패: '+result.stderr[-1000:])
    return {'graph':json.loads(result.stdout),'nodes':nodes,'active_edges':active,'active_joints':active_joints,
            'engine':subprocess.check_output([binary,'-V'],stderr=subprocess.STDOUT,text=True).strip()}


def draw(ax, figure, geometry):
    from matplotlib.path import Path
    from matplotlib.patches import PathPatch, Polygon
    graph=geometry['graph'];active=set(geometry['active_edges'][figure.id])
    for edge in graph.get('edges',[]):
        if edge['id'] not in active:continue
        for field in ['_draw_','_hdraw_']:
            for op in edge.get(field,[]):
                points=op.get('points',[])
                if op['op']=='b':
                    path=Path(points,[Path.MOVETO]+[Path.CURVE4]*(len(points)-1))
                    ax.add_patch(PathPatch(path,fill=False,color='black',lw=.9,
                        linestyle='--' if edge.get('arrowhead')=='tee' else '-'))
                elif op['op']=='P':ax.add_patch(Polygon(points,color='black'))
                elif op['op']=='L':ax.plot(*zip(*points),color='black',lw=.9)
    points={o['name']:tuple(map(float,o['pos'].split(','))) for o in graph['objects']}
    for joint in geometry['active_joints'][figure.id]:ax.plot(*points[joint],'ko',markersize=2.5)
    for node in figure.nodes:ax.text(*points[geometry['nodes'][node.id]],node.label,ha='center',va='center',fontsize=11)
    x0,y0,x1,y1=map(float,graph['bb'].split(','));ax.set_xlim(x0-4,x1+4);ax.set_ylim(y0-4,y1+4)
    ax.set_aspect('equal');ax.axis('off')
