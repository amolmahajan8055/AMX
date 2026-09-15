from html import escape

SECTIONS = {"Personalized summary:", "Strong areas (assessment only):", "Priority gaps (assessment only):", "Suggested learning plan:", "Your submitted profile and self-ratings:", "Complete assessment answer review:"}

def report_html(body):
    blocks=[]; in_list=False; question_open=False
    for raw in body.splitlines():
        line=raw.strip()
        if not line:
            if in_list: blocks.append('</ul>'); in_list=False
            continue
        clean=line.replace('**','')
        if clean.startswith('CodeKerdos |'):
            blocks.append('<div class="brand">CodeKerdos</div><h1>'+escape(clean.split(' - ',1)[-1])+'</h1>')
        elif clean.startswith('Q') and '. ' in clean and clean[1:clean.index('.')].isdigit():
            if in_list: blocks.append('</ul>'); in_list=False
            if question_open: blocks.append('</div>')
            blocks.append('<div class="question"><h3>'+escape(clean)+'</h3>'); question_open=True
        elif clean in SECTIONS or (line.startswith('**') and line.endswith('**')):
            if in_list: blocks.append('</ul>'); in_list=False
            if question_open and clean != 'Complete assessment answer review:': blocks.append('</div>'); question_open=False
            blocks.append('<h2>'+escape(clean.rstrip(':'))+'</h2>')
        elif clean.startswith('- '):
            if not in_list: blocks.append('<ul>'); in_list=True
            blocks.append('<li>'+escape(clean[2:])+'</li>')
        elif clean.startswith('Result:'):
            status='correct' if clean.endswith('Correct') else 'incorrect'
            blocks.append('<p class="'+status+'"><strong>'+escape(clean)+'</strong></p>')
        elif clean.startswith(('Your answer:','Correct answer:','Category:')):
            label,value=clean.split(':',1); blocks.append('<p class="answer"><strong>'+escape(label)+':</strong>'+escape(value)+'</p>')
        elif ': ' in clean and not question_open:
            label,value=clean.split(': ',1); blocks.append('<div class="row"><span>'+escape(label)+'</span><strong>'+escape(value)+'</strong></div>')
        else: blocks.append('<p>'+escape(clean)+'</p>')
    if in_list: blocks.append('</ul>')
    if question_open: blocks.append('</div>')
    styles='body{margin:0;background:#f3f6fa;color:#19243f;font-family:Arial,sans-serif;line-height:1.55}.wrap{max-width:760px;margin:auto;background:#fff;padding:32px}.brand{color:#007da8;font-size:18px;font-weight:700;border-left:7px solid #00b8ee;padding-left:10px}h1{font-size:25px;margin:12px 0 24px}h2{font-size:18px;margin:26px 0 10px;padding-bottom:7px;border-bottom:2px solid #e1e7ef}h3{font-size:15px;margin:0 0 12px}p{margin:7px 0}ul{margin:7px 0 14px;padding-left:22px}.row{display:flex;justify-content:space-between;gap:20px;padding:8px 0;border-bottom:1px solid #edf1f5}.row span{color:#5b677c}.question{margin:14px 0;padding:16px;border:1px solid #dce4ed;border-radius:8px;background:#fafbfd}.answer strong{display:inline-block;min-width:115px}.correct{color:#167548}.incorrect{color:#b42318}.footer{margin-top:30px;color:#68758a;font-size:12px}@media(max-width:600px){.wrap{padding:20px}.row{display:block}}'
    return '<!doctype html><html><head><meta charset="utf-8"><style>'+styles+'</style></head><body><div class="wrap">'+''.join(blocks)+'<div class="footer">CodeKerdos · AI Career &amp; Program Advisor</div></div></body></html>'
