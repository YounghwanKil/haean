"""Separate 30-question reading layout; never impersonates a reasoning Brief."""
import base64
import hashlib
import json
from pathlib import Path
from .hwp import execute, java_tool
from .pipeline import save


def validate_book(book):
    passages=book.get('passages',[])
    if len(passages)!=10: raise ValueError('언어이해는10지문×3문항이 필요합니다')
    numbers=[]
    for passage in passages:
        if not passage.get('paragraphs') or any(not x.strip() for x in passage['paragraphs']): raise ValueError('빈 지문')
        if len(passage['questions'])!=3: raise ValueError('지문당3문항이 필요합니다')
        for q in passage['questions']:
            numbers.append(q['number'])
            if len(q['options'])!=5 or len(set(q['options']))!=5: raise ValueError('5개 독립 선지 필요')
            if not 1<=q['answer']<=5 or len(q['option_explanations'])!=5: raise ValueError('정답·선지 해설 오류')
            if not q['stem'].strip() or not q['explanation'].strip(): raise ValueError('발문·해설 누락')
    if numbers!=list(range(1,31)): raise ValueError('문항번호1–30 순서 필요')
    return passages


def fill_reading(book_path,template,output,kind='questions',total_pages=None,page_starts=()):
    book_path,template,output=map(Path,(book_path,template,output))
    book=json.loads(book_path.read_text());passages=validate_book(book)
    if kind not in {'questions','solutions'}: raise ValueError('출력 종류 오류')
    if output.exists() or output.resolve()==template.resolve(): raise ValueError('기존 출력/원본 덮어쓰기 금지')
    if total_pages is not None and (kind!='questions' or not 1<=total_pages<=999):raise ValueError('문제지 쪽수1–999')
    if page_starts and (kind!='questions' or any(n not in range(2,31) for n in page_starts)): raise ValueError('새 쪽 시작은 문제지2–30번만 지정')
    output.parent.mkdir(parents=True,exist_ok=True)
    ir=output.with_suffix('.template.json');execute('convert',template.resolve(),'--to','json','-o',ir)
    styles={s['name']:i for i,s in enumerate(json.loads(ir.read_text())['header']['styles'])}
    enc=lambda text:base64.b64encode(text.encode()).decode()
    ops=[]
    def replace(a,b):ops.append('R\t'+enc(a)+'\t'+enc(b))
    title='해안 LEET 언어이해 검토용'
    replace('2026학년도 시대인재 LEET 시험지명 X회',title);replace('2027학년도 시대인재 LEET 시험지명 X회',title)
    replace('추리논증','언어이해');replace('제2교시','제1교시');replace('40문항','30문항');ops.append('C\t30')
    if total_pages:ops.append('N\t'+str(total_pages))
    def op(code,n,style,text,*extra):ops.append('\t'.join([code,str(n),str(styles[style]),enc(text),*map(str,extra)]))
    expected=[]
    for passage in passages:
        first=passage['questions'][0]['number'];last=first+2
        for q in passage['questions']:
            n=q['number']
            if kind=='questions':
                if n==first:
                    op('J',n,'문제',f'[{first}~{last}] 다음 글을 읽고 물음에 답하시오.')
                    op('L',n,'박스내용(들여쓰기)','\n\n'.join(passage['paragraphs']))
                    op('Q',n,'문제',q['stem']);expected.extend(passage['paragraphs'])
                else:
                    op('S',n,'문제',q['stem']);op('X',n,'박스내용(들여쓰기)','','flow')
                op('B',n,'보기내용(내어쓰기)',q.get('box',''),'keep')
                op('O',n,'선택지','\x1e'.join(f'{"①②③④⑤"[i]} {x}' for i,x in enumerate(q['options'])),'text','keep')
                expected.extend([q['stem'],q.get('box',''),*q['options']])
            else:
                op('H',n,'글 주제',passage['title']);op('A',n,'정답원문자','①②③④⑤'[q['answer']-1]);op('M',n,'해설정보표내부','\x1f'.join([q['difficulty'],passage['domain'],q['cognitive_task']]))
                op('T',n,'정오판단_설명',q['explanation']);expected.append(q['explanation'])
                for i,note in enumerate(q['option_explanations']):
                    op('T',n,'정오판단_선지','①②③④⑤'[i]+(' (정답)' if i+1==q['answer'] else ' (오답)'))
                    op('T',n,'정오판단_설명',note);expected.append(note)
    for number in sorted(set(page_starts)): ops.append('D\t'+str(number))
    spec=output.with_suffix('.fill.tsv');spec.write_text('\n'.join(ops)+'\n')
    java_tool('HaeanFill' if kind=='questions' else 'HaeanSolutions',template.resolve(),spec.resolve(),output.resolve())
    text=output.with_suffix('.txt');execute('convert',output,'-o',text)
    normalize=lambda s:''.join(s.replace('<u>','').replace('</u>','').split())
    rendered=normalize(text.read_text());missing=[x[:80] for x in expected if normalize(x) not in rendered]
    if missing:raise ValueError('재읽기 내용 누락: '+str(missing))
    receipt={'scope':'LEET reading experimental full30 layout','kind':kind,'book_sha256':hashlib.sha256(book_path.read_bytes()).hexdigest(),'template_sha256':hashlib.sha256(template.read_bytes()).hexdigest(),'hwp_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'questions':30,'passages':10,'page_starts':sorted(set(page_starts)),'total_pages_label':total_pages,'reread_content_verified':True,'native_visual_verified':False,'human_approved':False}
    save(output.with_suffix('.receipt.json'),receipt);return receipt


def main():
    import argparse
    parser = argparse.ArgumentParser(description="실험용 LEET 언어이해 10지문·30문항 양식 삽입")
    parser.add_argument("book", type=Path)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--kind", choices=["questions", "solutions"], default="questions")
    parser.add_argument("--total-pages", type=int)
    parser.add_argument("--page-start", type=int, action="append", default=[])
    args = parser.parse_args()
    print(json.dumps(fill_reading(args.book, args.template, args.out, args.kind, args.total_pages, args.page_start), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
