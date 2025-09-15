# 【非公式】PLATEAU API MCP

[Project PLATEAU](https://www.mlit.go.jp/plateau/)において試験運用中の[PLATEAU API](https://api.plateauview.mlit.go.jp/docs/)を活用し、ユーザーが自然言語を用いてPLATEAUデータの検索・ダウンロードおよびQGISでの表示を可能とするMCPサーバーです。
<br/>


## 注意事項  
- __あくまで個人が趣味で開発したものです__   
- このツールを利用したことによって生じたいかなる損害についても、作成者は責任を負いかねます  
- 実行中に、`Could not connect to MCP server`というメッセージが表示されることがありますが、動作に影響はないことを確認しています。  
    この部分に関しては、追って修正版をリリースする予定です。  
<br/>  


## 機能
Claude for DesktopなどのMCPホスト上で、ユーザーの自然言語入力による以下の要望の実現を支援します。
- 緯度・経度を地域メッシュコードへ変換
- 地域メッシュコードや自治体コードを用いたPLATEAUデータの検索・ダウンロード
- QGISおよび[QGISMCP](https://github.com/jjsantos01/qgis_mcp)、[PLATEAU QGIS Plugin](https://plugins.qgis.org/plugins/plateau_plugin/)を用いたダウンロードデータの可視化
<br/>


## Tools
現在、以下の機能を実装しています。  

### get_mesh_code
緯度経度から指定レベルのメッシュコードを取得。  
**入力**: 
- `lat`: (float) 緯度
- `lon`: (float) 経度
- `mesh_order`: (int) メッシュレベル（1～5）（デフォルト: 2）  

**出力**: (str) メッシュコード  

### get_list_citygml
指定条件でCityGMLファイル一覧を取得し、指定された地物のURLリストを提供。  
**入力**: 
- `conditions`: (str) 三次メッシュコード（例: 'm:53394611'）または自治体コード（例: '13101'）  
- `feature_type`: (str) `bldg`のような地物の記号  

**出力**: (List[str]) 指定された地物のURLリスト  

### pack_citygml
URLリストをZIP化する非同期リクエストを送信。  
**入力**: 
- `urls`: (List[str]) CityGMLファイルのダウンロードURLのリスト  

**出力**: (Dict[str, Any]) リクエストIDを含むレスポンス  

### get_pack_status
ZIP生成の進捗・ステータスを取得。  
**入力**: 
- `id`: (str) packリクエストのID  

**出力**: (Dict[str, Any]) ステータス情報  

### get_pack_download
指定されたリクエストIDに対応するZIPファイルのダウンロードURLを取得。  
**入力**: 
- `id`: (str) packリクエストのID  

**出力**: (Dict[str, Any]) ダウンロード用URL等を含むレスポンス  

### download_files
指定されたダウンロードURLからZIPファイルを非同期でダウンロード。  
**入力**: 
- `download_url`: (str) ダウンロード対象のURL  
- `save_dir`: (str) ダウンロード先のディレクトリパス  
- `mesh_code`: (str) メッシュコード（オプション）  
- `feature_types`: (List[str]) 地物種別のリスト（オプション）  
- `auto_extract`: (bool) 自動展開フラグ（デフォルト: True） 

**出力**: (Dict[str, Any]) ダウンロード結果の詳細情報  

### get_attributes
指定されたCityGMLファイルの属性情報を取得。  
**入力**: 
- `url`: (str) CityGMLファイルのURL  
- `id`: (str) 取得対象の属性ID  
- `skip_code_list_fetch`: (bool) コードリスト再取得スキップフラグ  

**出力**: (Dict[str, Any]) 属性情報  

### get_features
指定されたCityGMLファイルの地物IDリストを取得。  
**入力**:   
- `url`: (str) CityGMLファイルのURL  
- `sid`: (str) 空間ID  

**出力**: (Dict[str, Any]) 地物IDリスト  

### get_spatialid_attributes
空間IDごとの属性情報を取得。  
**入力**: 
- `sid`: (str) 空間ID  
- `type`: (str) 属性の種類（例: 'Building'）  
- `skip_code_list_fetch`: (bool) コードリスト再取得スキップフラグ  

**出力**: (Dict[str, Any]) 空間IDごとの属性情報  

### show_qgis_download_citygml
PLATEAUのCityGMLをQGIS上で表示するコマンドを生成し実行。  
`QGISMCP`および`PLATEAU QGIS Plugin`が必要。  
**入力**:   
- `citygml_path`: (str) 表示対象のCityGMLのパス  
- `lod_preference`: (int) 表示するLODの指定（デフォルト: 0）  
- `semantic_parts`: (bool) 地物構成要素ごとのレイヤ分割フラグ（デフォルト: False）  

**出力**: (str) QGIS上でCityGMLを表示するためのPythonコマンド  


<br/>


## 使い方
Windows版Claude for Desktopで動作確認を行っているため、その他のOSやアプリにして使用する場合は、ご自身で使用方法の調査をお願いします。  
また、クローンして使用する方法のほか、試験的にビルド済みのWheelファイルを用いた方法も記載しております。

### uvをインストール
`uv`を用いてPythonの環境構築を行っています。  
uvをインストールしていない場合は、以下に従いインストールしてください。  
Powershellを**管理者**として起動し、以下のコマンドを実行  
```Powershell
winget install --id astral-sh.uv
```

### A. リポジトリをクローンし使用（推奨）
#### 1. リポジトリをクローンする  
```bash
git clone https://github.com/raokiey/plateau-api-mcp.git
```

#### 2. Claude for Desktopの設定  
Claude for Desktopの設定ファイルに以下を追加してください。  
設定ファイルのパスは以下の通りです。  
`%AppData%\Claude\claude_desktop_config.json`  

以下は、`C:\work\`にクローンしたときの例です。  
設定ファイル中のパスは、 **\\** ではなく、 **/** であることに注意してください。  

```json
{
    "mcpServers": {
        "plateau-api": {
            "command": "uvx",
            "args": [
                "--from",
                "C:/work/plateau-api-mcp",
                "plateau-api-mcp"
            ]
        }
    }
}
```
Claude for Desktopを起動し、ツールに`plateau-api`があることを確認してください。


### B. ビルド済みのWheelファイルを使用（試験段階）
#### Claude for Desktopの設定  
`%AppData%\Claude\claude_desktop_config.json` を以下のように設定してください。
```json
{
    "mcpServers": {
        "plateau-api": {
            "command": "uvx",
            "args": [
                "-p", "3.12",
                "--from",
                "https://github.com/raokiey/plateau-api-mcp/releases/download/v0.1.0/plateau_api_mcp-0.1.0-py3-none-any.whl",
                "plateau-api-mcp"
            ]
        }
    }
}
```
Claude for Desktopを起動し、ツールに`plateau-api`があることを確認してください。
<br/>


## 使用例
```text
沼津駅周辺のPLATEAUの建物データと道路データをダウンロードし、`C:\work\plateau-api-mcp\sample_data`に格納してください。
また、ダウンロードしたデータをQGISに表示してください。
```
<br/>


## ライセンス
本プロジェクトは Apache License 2.0 の下で提供します。  
詳細は [`LICENSE`](./LICENSE) をご覧ください。

また、本プロジェクトは以下のOSSに依存しています。各OSSのライセンスは、それぞれの LICENSE/NOTICE に従います。  
- **[aiofiles](https://github.com/Tinche/aiofiles)** — Apache-2.0  
- **[HTTPX](https://github.com/encode/httpx)** — BSD-3-Clause  
- **[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)** — MIT  
