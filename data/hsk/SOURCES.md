# HSK 3.0 词表数据来源

本目录词表由 `scripts/fetch_hsk30.py` 从以下官方来源自动抓取生成，非人工编造：

1. 《国际中文教育中文水平等级标准》GF 0025—2021（中华人民共和国教育部、国家语言文字工作委员会，2021-03-24 发布，2021-07-01 实施）。
   PDF：https://www.moe.gov.cn/jyb_sjzl/ziliao/A19/202111/W020211118507389477190.pdf
2. 汉考国际官方查询接口（新 HSK 词表）：
   https://admin.chinesetest.cn/newhsk/standardsAction.do?means=getStandardWordsList

共 11092 条，按「三等九级」分级：一级~六级各自独立，七~九级合并为「高等」(HSK7.txt)。
用途：为 Panda News 阅读材料做难度分级与生词标注。数据为事实性参考信息，
本工具不声称等同于官方考试，引用时请保留本出处说明。

生成时间：2026-11-12 10:46:15
