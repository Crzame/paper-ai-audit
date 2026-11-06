import hashlib,json,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from docx_extract import extract

class ReadOnlyDocxChecks(unittest.TestCase):
    def test_table_deletions_and_reference_tail_do_not_enter_eligible_text(self):
        xml='''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
        <w:p><w:r><w:t>测试标题</w:t></w:r></w:p>
        <w:p><w:r><w:t>摘要：摘要正文内容。</w:t></w:r></w:p>
        <w:p><w:r><w:t>一、引言</w:t></w:r></w:p>
        <w:p><w:r><w:t>正文起点。</w:t></w:r><w:del><w:r><w:delText>被删除的文字</w:delText></w:r></w:del><w:r><w:t>正文尾部。</w:t></w:r></w:p>
        <w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格内容不参与正文分类</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
        <w:p><w:r><w:t>参考文献</w:t></w:r></w:p>
        <w:p><w:r><w:t>不属于正文的参考内容</w:t></w:r></w:p>
        </w:body></w:document>'''
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'sample.docx'
            with zipfile.ZipFile(source,'w') as archive:archive.writestr('word/document.xml',xml)
            before=hashlib.sha256(source.read_bytes()).hexdigest()
            result=extract(source,'sample',root/'out')
            text=Path(result['text_path']).read_text(encoding='utf-8')
            self.assertEqual(text,'摘要：摘要正文内容。\n\n正文起点。正文尾部。')
            self.assertEqual(before,hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(result['exclusions']['table_cell'],1)
            self.assertEqual(result['exclusions']['references_and_backmatter'],2)

if __name__=='__main__':unittest.main(verbosity=2)
