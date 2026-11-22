# 陶瓷基片厂双站复产演练台账

设备员把同一班次的候选工况和作业窗交给上、下游工艺员。两站串联，只有实际同时可作业的时段才计入生产线恢复小时。质控值班员在站端关库后，使用指定的两份实收件核账。下一班档案员可以按报告号取回当时签存的结论、父件和成功回执。

## 运行

在项目根目录使用 Python 3.11，依赖均为标准库。

```sh
python3 -B check_project.py
python3 -B demo.py
python3 -B incident.py
```

`check_project.py` 由控制台物化。直接运行完整套件的命令为 `python3 -B -m unittest discover -s tests -t .`。演示使用独立的临时站库和中心库。上游仅在完成甲检修后于 `[0,1)` 作业，下游原版作业窗为 `[1,2)`，勘误后为 `[1/2,3/2)`。关站后两次签发，重开中心后分别取回甲收益为 `[0,0]` 与 `[1/2,1/2]` 的定稿，乙均为 `[0,0]`。`incident.py` 独立核对两项均为 `[1/2,1/2]` 的双候选演练，并在业务偏差时非零退出。

## 工单与班次

`station.shifts.Shift(shift_id, start, end)` 定义班次值。班次标识和两端坐标均相同的双站件才可合用。时段 `[start,end)` 长度必须为正并位于班次内。API 接受整型、`Fraction` 或可被 `Fraction` 精确解析的文本小时数。站件和定稿用有理数字符串表示小时。标识使用非空文本，首尾无空白。

工单是具备以下字段的字典。`devices` 声明工单中的设备条件，`candidates` 列出一至四个带各自内部 ID 的候选及其启用的设备条件。`rules` 列出作业规则，可为空。每条规则在所列检修选择中且所需条件均已启用时生效。`none`、`A`、`B`、`AB` 依次表示不修、仅甲、仅乙和两项均修。未获得生效时段时对应空列表。生效时段取并集，相交或相接的时段合为一段。登记时校验所有时段，包括不在任一候选中生效的规则。

```python
order = {
    'workorder_id': '工单-01',
    'devices': ['设备-02'],
    'candidates': [{'id': '工况-01', 'enabled': ['设备-02']}],
    'rules': [{
        'id': '规则-01',
        'requires': ['设备-02'],
        'choices': ['A', 'AB'],
        'windows': [['0', '1'], ['3/2', '2']],
    }],
}
```

## 工艺员、值班员和档案员的调用顺序

1. 站端打开站库连接，依次调用 `RevisionStore(conn).initialize()` 和 `IssueCatalog(conn).initialize()`。调用 `station.workorders.record(store, station, shift, order)` 得到修订号。`store.get(station, revision_number)` 按站读取固定修订。
2. 调用 `issue.evidence.freeze(catalog, station, revision_number)` 得到 `FrozenEvidence`。同一站点和修订号重复冻结返回固定的 `issue_id` 和 `original`。原工单校验失败抛 `WorkorderError`，未知修订抛 `RevisionNotFound`。
3. 中心打开中心库，依次调用 `EvidenceRegistry(conn).initialize()` 和 `ReportLedger(conn).initialize()`。调用 `receive.registry.accept(registry, evidence.original)` 得到整数实收号。校验和实收在中心完成，原件可通过文件传递。`EvidenceError` 表示原件格式非法，`IntakeConflict` 表示有效原件与既有发行身份冲突。已接纳的原件原样保留，逐字节重传返回相同实收号。
4. 站库连接关闭后，调用 `reports.publish.publish(ledger, first_received_id, second_received_id)`。成功返回 `PublishedReport`，包括 `snapshot.report_number`、`snapshot.parents`、`snapshot.credits.a`、`snapshot.credits.b` 和 `receipt`。父件顺序与请求一致，各含实收号、发行号、站点、班次和原件 SHA-256。缺件、同站或错班抛 `SelectionError`。签存写入或提交失败抛 `PublishError`，报告及成功回执均无新增。
5. 工艺员对指定修订调用 `station.corrections.correct(store, station, revision_number, changes)`。`changes` 是非空列表，每项形如 `{'rule_id': '规则-01', 'window_index': 0, 'window': ['1/2','5/4']}`。下标从零开始，按该修订中规则的原时段顺序定位。重复修改同一位置、未知规则、越界下标或非法新版抛 `WorkorderError`。合法勘误追加带父号的修订，其余字段沿用原修订。
6. 冻结并实收勘误件。再次签发时用新实收号明确指定新件。旧实收件仍可显式选用。
7. 档案员重开中心库，调用 `reports.history.read(ledger, report_number)` 领取原定稿和回执。未知号抛 `ReportNotFound`。领取直接读取已经提交的报告。

调用方持有并关闭 SQLite 连接。以上操作使用空闲连接，写入由对应账簿开启并提交事务。同一个连接按顺序使用。初始化可重复执行，只补齐账结构，站点记录、已发行原件、实收件和已签报告均保留。

## V1 原件与收益口径

原件是 UTF-8 JSON 字节，外层含 `version`（整数 `1`）、`issue_id`、`station`、`shift` 和 `body`。`shift` 含文本 `id`、`start`、`end`。`body.candidates` 是一至四条匿名响应，每条响应含全部四种选择，各值是 `[start,end]` 字符串对的列表。候选身份由件内整条响应的归属确定。发行正文只公开作业时段，站内发行账保留修订出处。发行号唯一，原件指纹由中心按实际实收字节计算。

独立选取每站的一个候选。固定这一对候选，在四种检修选择下分别取两站可作业并集的交集长度 `F0, FA, FB, FAB`。甲收益是 `((FA-F0)+(FAB-FB))/2`，乙收益是 `((FB-F0)+(FAB-FA))/2`。每项的正式范围是所有实际候选对中该项收益的最小值和最大值。无重合时计零，双方时段仅在端点相接时同样计零。

原套件涵盖工单准入、候选响应及冻结重取、实收冲突、显式选件、等边缘不同收益、候选笛卡尔积、多段交集、局部勘误、精确历史、重复初始化及真实 SQLite 提交回滚。业务预期由样例时段和检修顺序手算给出。
