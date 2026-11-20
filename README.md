# MediaHubTV 影视资源配置

只维护接口清单；影片目录由资源站 API 实时提供。无需修改或重装软件。

## 导入链接

https://raw.githubusercontent.com/Zkadwnnxu/MediaHubTV-resources/data/vod.json

在 MediaHubTV → 设置 → 影视点播接口 → 添加链接，粘贴上述地址，识别并预览后保存。保留原来的订阅和自定义源。以后重新加载/更新此订阅即可读取新清单。

本次检查：用户给出的23项中，14项通过分类、列表及直接HLS剧集元数据检查；其中12项搜索检查通过，其余2项关闭搜索标志。未通过的9项没有加入默认清单，地址和原因仍保留在catalog.json及检查报告。

检查报告：https://raw.githubusercontent.com/Zkadwnnxu/MediaHubTV-resources/data/health.json

数据检查不读取视频流，不能等同于电视实播或流畅性保证。网络和站点状态会变化。

## 维护

- catalog.json：原始公开站点、官方帮助页、已核对的候选接口。key保持稳定。
- scripts/update.py：仅请求帮助页与CMS元数据，不下载插件、封面或媒体，不执行远程代码。
- .github/workflows/catalog.yml：每6小时或手动检查，仅向data分支写vod.json和health.json，软件源码与main不受自动数据提交影响。
- 临时失败保留上次地址；连续3轮失败后移出默认清单，原地址保留，恢复后自动加入。若整体失联，保留上次非空清单并在报告注明。
- 新地址仅从该站明确登记的官方帮助页提取，通过CMS类别/详情和直接HLS元数据检查才采用；无法识别新官网时仍需人工改catalog.json。
- 定时工作流需要维护代码PR审核合并main后才会生效；未合并前，固定JSON链接已可使用，但不会自动更新。不需要用户提供额外密钥。

本地验证：`python3 -m unittest discover -s tests -v`。真实元数据检查：`python3 scripts/update.py --output published`。

公开仓库仅包含公开接口与检查结果，不含MediaHubTV软件源码、用户歌单、观看记录、凭据或本机配置。
