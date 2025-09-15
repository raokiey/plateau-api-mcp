import asyncio
import os
import shutil
import zipfile
import logging
from typing import Any, Dict, List, TypedDict

import aiofiles
import httpx
from mcp.server.fastmcp import FastMCP

# ロガーの設定
logger = logging.getLogger("plateau-api")
logger.setLevel(logging.INFO)

# 標準エラー出力へのハンドラを追加
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

# MCPサーバーの初期化
mcp = FastMCP("PLATEAU-API")

# PLATEAU APIのエンドポイント
END_POINT = "https://api.plateauview.mlit.go.jp"


class PackResponse(TypedDict):
    id: str

async def fetch_api(
    path: str,
    method: str = "GET",
    params: Dict[str, Any] = None,
    json_body: Dict[str, Any] = None,
    retries: int = 3,
    headers: Dict[str, str] = None,
    expect_json: bool = True  # JSON解析を期待するかどうかの新しいパラメータ
) -> Any:
    """
    共通のHTTPリクエストヘルパー。

    指定されたエンドポイントに対してHTTPリクエストを送信し、レスポンスをJSON形式で返します。
    GETまたはPOSTメソッドをサポートします。

    Args:
        path (str): APIエンドポイントのパス。
        method (str): HTTPメソッド（"GET"または"POST"）。デフォルトは"GET"。
        params (Dict[str, Any], optional): クエリパラメータ。デフォルトはNone。
        json_body (Dict[str, Any], optional): POSTリクエスト時のJSON Body。デフォルトはNone。
        retries (int): エラー発生時のリトライ回数。デフォルトは3。
        headers (Dict[str, str], optional): カスタムヘッダー。デフォルトはNone。
        expect_json (bool): JSONレスポンスを期待する場合はTrue。デフォルトはTrue。

    Returns:
        Any: レスポンスのJSONデータまたは生レスポンス。
    """
    url = END_POINT + path

    # デフォルトヘッダーを設定
    if headers is None:
        headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for attempt in range(retries):
            try:
                if method.upper() == "GET":
                    resp = await client.get(url, headers=headers, params=params)
                else:
                    resp = await client.post(url, headers=headers, json=json_body)
                resp.raise_for_status()

                if expect_json:
                    return resp.json()
                else:
                    # JSON以外のレスポンスの場合は生レスポンスを返す
                    return resp
            except httpx.HTTPStatusError as e:
                error_details = resp.text
                logger.error(f"HTTPエラー発生: {e}. 詳細: {error_details}")
                if resp.status_code == 403:
                    logger.error("403 Forbiddenエラー: アクセス権限を確認してください。")
                if attempt < retries - 1:
                    logger.info(f"リトライ中... ({attempt + 1}/{retries})")
                    await asyncio.sleep(2)  # リトライ間隔を2秒に設定
                else:
                    raise RuntimeError(f"APIリクエスト失敗: {e}. 詳細: {error_details}")
            except Exception as e:
                logger.error(f"予期しないエラーが発生しました: {e}")
                raise


@mcp.tool()
async def get_mesh_code(lat: float, lon: float, mesh_order: int = 2) -> str:
    """
    緯度経度から指定レベルのメッシュコードを取得。ユーザから指定が無い限りは2次メッシュコードを返す。

    なお、入力する緯度経度の値がおおざっぱな場合は、ユーザが与えた地域名などをWeb検索し、具体的な値とすること。

    Args:
        lat (float): 緯度（度）
        lon (float): 経度（度）
        mesh_order (int): メッシュレベル（1～5）を指定。デフォルトは4。
                         1: 1次メッシュ（約80km四方）
                         2: 2次メッシュ（約10km四方）
                         3: 3次メッシュ（約1km四方）
                         4: 4次メッシュ（約500m四方）
                         5: 5次メッシュ（約250m四方）

    Returns:
        str: メッシュコード

    Raises:
        ValueError: 入力値が範囲外の場合
    """
    # 入力値検証
    if not (20 <= lat <= 46):
        raise ValueError("緯度は20～46度の範囲で入力してください（日本の範囲）")
    if not (122 <= lon <= 154):
        raise ValueError("経度は122～154度の範囲で入力してください（日本の範囲）")
    if not (1 <= mesh_order <= 5):
        raise ValueError("mesh_orderは1～5の値を指定してください")

    # 1次メッシュコード計算（約80km四方）
    # 緯度: 40分（2/3度）単位で分割
    # 経度: 1度単位で分割
    lat_first_code = int(lat * 60 // 40)  # 緯度方向のコード（40分単位）
    lon_first_code = int(lon - 100)       # 経度方向のコード（東経100度からの差）
    mesh_code = f"{lat_first_code:02d}{lon_first_code:02d}"

    if mesh_order == 1:
        return mesh_code

    # 2次メッシュコード計算（約10km四方）
    # 1次メッシュを緯度・経度方向に8分割
    lat_remainder_1st = lat * 60 - lat_first_code * 40  # 1次メッシュ内での緯度残り（分）
    lat_second_code = int(lat_remainder_1st // 5)       # 緯度方向のコード（5分単位）

    lon_remainder_1st = lon - 100 - lon_first_code      # 1次メッシュ内での経度残り（度）
    lon_second_code = int(lon_remainder_1st * 60 // 7.5)  # 経度方向のコード（7.5分単位）

    mesh_code += f"{lat_second_code}{lon_second_code}"

    if mesh_order == 2:
        return mesh_code

    # 3次メッシュコード計算（約1km四方）
    # 2次メッシュを緯度・経度方向に10分割
    lat_remainder_2nd = lat_remainder_1st - lat_second_code * 5  # 2次メッシュ内での緯度残り（分）
    lat_third_code = int(lat_remainder_2nd * 60 // 30)           # 緯度方向のコード（30秒単位）

    lon_remainder_2nd = lon_remainder_1st * 60 - lon_second_code * 7.5  # 2次メッシュ内での経度残り（分）
    lon_third_code = int(lon_remainder_2nd * 60 // 45)                  # 経度方向のコード（45秒単位）

    mesh_code += f"{lat_third_code}{lon_third_code}"

    if mesh_order == 3:
        return mesh_code

    # 4次メッシュコード計算（約500m四方）
    # 3次メッシュを緯度・経度方向に2分割
    lat_remainder_3rd = lat_remainder_2nd * 60 - lat_third_code * 30  # 3次メッシュ内での緯度残り（秒）
    lat_fourth_index = int(lat_remainder_3rd // 15)                   # 緯度方向の分割インデックス（15秒単位）

    lon_remainder_3rd = lon_remainder_2nd * 60 - lon_third_code * 45  # 3次メッシュ内での経度残り（秒）
    lon_fourth_index = int(lon_remainder_3rd // 22.5)                 # 経度方向の分割インデックス（22.5秒単位）

    # 4次メッシュは2x2の4分割を1〜4の番号で表現
    fourth_mesh_number = lat_fourth_index * 2 + lon_fourth_index + 1
    mesh_code += str(fourth_mesh_number)

    if mesh_order == 4:
        return mesh_code

    # 5次メッシュコード計算（約250m四方）
    # 4次メッシュを緯度・経度方向に2分割
    lat_remainder_4th = lat_remainder_3rd - lat_fourth_index * 15     # 4次メッシュ内での緯度残り（秒）
    lat_fifth_index = int(lat_remainder_4th // 7.5)                  # 緯度方向の分割インデックス（7.5秒単位）

    lon_remainder_4th = lon_remainder_3rd - lon_fourth_index * 22.5   # 4次メッシュ内での経度残り（秒）
    lon_fifth_index = int(lon_remainder_4th // 11.25)                # 経度方向の分割インデックス（11.25秒単位）

    # 5次メッシュは2x2の4分割を1〜4の番号で表現
    fifth_mesh_number = lat_fifth_index * 2 + lon_fifth_index + 1
    mesh_code += str(fifth_mesh_number)

    return mesh_code


@mcp.tool()
async def get_list_citygml(conditions: str, feature_type: str) -> List[str]:
    """
    指定条件でCityGMLファイル一覧を取得し、指定された地物のURLリストを返します。

    複数のCityGMLがある場合は、ユーザから指定がない限り対象範囲に出来るだけ絞った最新のURLを取得します。
    例: 取得したい3次メッシュコードが`51357399`でヒットしなく、自治体コードでヒットした場合は、
    その中の`51357399`に対応する最新のURLを取得します。
    指定された条件（メッシュコードもしくは自治体コード）に基づいて、CityGMLファイルのリストを取得し、
    指定された地物のURLのみをフィルタリングして返します。

    Args:
        conditions (str): 
            - 三次メッシュコード (例: 'm:53394611')  
            - 自治体コード (例: '13101')  
        feature_type (str): ダウンロードしたい地物の記号。以下のいずれかを指定してください。
            - 'bldg': 建築物
            - 'tran': 道路
            - 'brid': 橋梁
            - 'urf': 都市計画決定情報
            - 'luse': 土地利用
            - 'fld': 洪水浸水想定区域
            - 'tnm': 津波浸水想定
            - 'lsld': 土砂災害警戒区域
            - 'htd': 高潮浸水想定区域
            - 'ifld': 内水浸水想定区域
            - 'frn': 都市設備
            - 'veg': 植生
            - 'dem': 地形（起伏）

    Returns:
        List[str]: 指定された地物のURLリスト。該当するURLがない場合は空のリストを返します。
    """
    # APIからCityGMLファイル一覧を取得
    response = await fetch_api(f"/datacatalog/citygml/{conditions}")
    filtered_urls = []

    # 指定された地物のURLのみをフィルタリング
    for city in response.get("cities", []):
        files = city.get("files", {}).get(feature_type, [])
        filtered_urls.extend(file["url"] for file in files)

    # URLリストが空の場合の処理
    if len(filtered_urls) == 0:
        logger.warning(f"指定された条件 '{conditions}' に対して地物 '{feature_type}' のデータが見つかりませんでした。")
        return []

    return filtered_urls


@mcp.tool()
async def pack_citygml(urls: List[str]) -> PackResponse:
    """
    指定されたCityGMLファイルのURLリストをZIPファイルにまとめるリクエストを送信。

    Args:
        urls (List[str]): CityGMLファイルのダウンロードURLのリスト。

    Returns:
        Dict[str, Any]: リクエストID等を含むレスポンス。リクエストIDは、`id`キーで取得できます。
    """
    return await fetch_api("/citygml/pack", method="POST", json_body={"urls": urls})


@mcp.tool()
async def get_pack_status(id: str) -> Dict[str, Any]:
    """
    CityGMLのZIP化ステータス取得API: ZIP生成の進捗・ステータスを取得します。

    指定されたリクエストIDに対応するZIP生成の進捗状況やステータスを取得します。

    Args:
        id (str): packリクエストのID。

    Returns:
        Dict[str, Any]: ステータス情報。
                        ステータス情報は以下の通りです。
                        - "accepted": リクエスト受理
                        - "processing": 処理中
                        - "succeeded": 成功
                        - "failed": 失敗
    """
    return await fetch_api(f"/citygml/pack/{id}/status")


@mcp.tool()
async def get_packed_download_url(id: str) -> Dict[str, Any]:
    """
    ZIP化したCityGMLのダウンロードURLを取得。

    指定されたリクエストIDに対応するZIPファイルのダウンロードURLを取得します。

    Args:
        id (str): packリクエストのID。

    Returns:
        Dict[str, Any]: ダウンロード用URL等を含むレスポンス。
    """
    # ダウンロードURL取得時はContent-Typeヘッダーを除去し、JSONを期待しない
    custom_headers = {}  # 空のヘッダーを使用
    resp = await fetch_api(f"/citygml/pack/{id}.zip", headers=custom_headers, expect_json=False)

    # レスポンスからダウンロードURLを構築
    download_url = str(resp.url)
    return {
        "download_url": download_url,
        "status": "ready",
        "content_type": resp.headers.get("content-type", "application/zip")
    }


@mcp.tool()
async def download_files(download_url: str, save_dir: str, mesh_code: str = None, feature_types: List[str] = None, auto_extract: bool = True) -> Dict[str, Any]:
    """
    指定されたダウンロードURLからZIPファイルを非同期でダウンロード。

    `get_packed_download_url`で取得したダウンロードURLを使用してZIPファイルをダウンロードします。

    Args:
        download_url (str): ダウンロード対象のURL（get_pack_downloadで取得したURL）。
        save_dir (str): ダウンロード先のディレクトリパス。
        mesh_code (str, optional): メッシュコード。ファイル名生成に使用。
        feature_types (List[str], optional): 地物種別のリスト（例: ['bldg', 'brid']）。ファイル名生成に使用。
        auto_extract (bool): ダウンロード後に自動でGMLファイルを展開する場合はTrue。デフォルトはFalse。

    Returns:
        Dict[str, Any]: ダウンロード結果の詳細情報
            - zip_path: ダウンロードしたZIPファイルのパス
            - extract_result: auto_extractがTrueの場合の展開結果（`_extract_citygml_files`関数の戻り値）
    """
    # ダウンロード先ディレクトリを作成
    os.makedirs(save_dir, exist_ok=True)

    # 意味のあるファイル名を生成
    if mesh_code and feature_types:
        from datetime import datetime

        # 現在の日付を取得（yyyymmdd形式）
        current_date = datetime.now().strftime("%Y%m%d")
        # 地物種別を結合（例: "bldg-brid"）
        feature_str = "-".join(sorted(feature_types))
        # ファイル名を生成: {メッシュコード}_{地物種別}_{yyyymmdd}.zip
        filename = f"{mesh_code}_{feature_str}_{current_date}.zip"
    else:
        # メッシュコードや地物種別が指定されていない場合はURLから抽出
        from urllib.parse import unquote, urlparse
        parsed_url = urlparse(download_url)
        filename = os.path.basename(parsed_url.path)
        filename = unquote(filename)

        # ファイル名が取得できない場合はデフォルト名を使用
        if not filename or not filename.endswith('.zip'):
            filename = "plateau_data.zip"

    save_path = os.path.join(save_dir, filename)

    async with httpx.AsyncClient() as client:
        logger.info(f"ダウンロード中: {download_url} -> {save_path}")
        try:
            # ZIPファイルを非同期でダウンロード
            response = await client.get(download_url)
            response.raise_for_status()

            async with aiofiles.open(save_path, mode="wb") as f:
                await f.write(response.content)

            logger.info(f"ダウンロード完了: {save_path}")

            # 結果を格納する辞書
            result = {
                "zip_path": save_path,
                "success": True
            }

            # 自動展開が有効な場合はGMLファイルを展開
            if auto_extract:
                logger.info("自動展開を開始...")
                extract_result = await _extract_gml_files_flat(save_path)
                result["extract_result"] = extract_result
                logger.info(f"自動展開完了: {extract_result['total_files']}個のGMLファイルを展開")

            return result

        except Exception as e:
            # ダウンロード失敗時のエラーメッセージ
            error_msg = f"ダウンロード失敗: {download_url}. エラー: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)


@mcp.tool()
async def get_attributes(
    url: str,
    id: str,
    skip_code_list_fetch: bool = False
) -> Dict[str, Any]:
    """
    CityGMLの属性情報を取得。

    指定されたCityGMLファイルのURLと属性IDに基づいて、属性情報を取得します。
    コードリストの再取得をスキップするオプションも提供します。

    Args:
        url (str): CityGMLファイルのURL。
        id (str): 取得対象の属性ID。
        skip_code_list_fetch (bool): コードリストの再取得をスキップする場合はTrue。

    Returns:
        Dict[str, Any]: 属性情報。
    """
    params = {"url": url, "id": id}
    if skip_code_list_fetch:
        params["skip_code_list_fetch"] = "true"
    return await fetch_api("/citygml/attributes", params=params)


@mcp.tool()
async def get_features(url: str, sid: str) -> Dict[str, Any]:
    """
    CityGMLのFeature IDを取得。

    指定されたCityGMLファイルのURLと空間IDに基づいて、地物IDのリストを取得します。

    Args:
        url (str): CityGMLファイルのURL。
        sid (str): 空間ID。

    Returns:
        Dict[str, Any]: 地物IDリスト。
    """
    return await fetch_api("/citygml/features", params={"url": url, "sid": sid})


@mcp.tool()
async def get_spatialid_attributes(
    sid: str,
    type: str,
    skip_code_list_fetch: bool = False
) -> Dict[str, Any]:
    """
    CityGML空間ID属性まとめ取得API。

    指定された空間IDと属性の種類に基づいて、空間IDごとの属性情報を取得します。
    コードリストの再取得をスキップするオプションも提供します。

    Args:
        sid (str): 空間ID。
        type (str): 属性の種類 (例: 'Building')。
        skip_code_list_fetch (bool): コードリストの再取得をスキップする場合はTrue。

    Returns:
        Dict[str, Any]: 空間IDごとの属性情報。
    """
    params = {"sid": sid, "type": type}
    if skip_code_list_fetch:
        params["skip_code_list_fetch"] = "true"
    return await fetch_api("/citygml/spatialid_attributes", params=params)


class QGISCommand:
    def __init__(self):
        self._initialized = False
        self._qgis_available = False

    async def initialize(self):
        """QGISとの接続を初期化する"""
        if self._initialized:
            return

        # 初期化フラグを設定
        self._initialized = True
        
        # このMCPサーバーはQGISMCPとは直接通信せず、
        # コマンド文字列を生成するだけです。
        # 実際のQGIS通信はClaude for Desktopを介して行われます。
        self._qgis_available = True
        logger.info("QGISコマンド生成の準備が完了しました")

    def is_available(self) -> bool:
        """QGISが利用可能かどうかを返す"""
        return self._qgis_available

# QGISコマンドのインスタンスを生成
qgis_command = QGISCommand()

@mcp.tool()
async def show_qgis_download_citygml(
    citygml_path: str,
    lod_preference: int = 0,
    semantic_parts: bool = False
) -> Dict[str, Any]:
    """
    PLATEAUのCityGMLをQGIS上で表示するコマンドを生成。

    指定されたCityGMLファイルをQGIS上で表示するためのPythonコマンドを生成します。
    ダウンロードしたCityGMLファイルや指定されたCityGMLをQGISで表示する際は、はじめは必ずこの関数を使用してください。
    QGISに「PLATEAU QGIS Plugin」プラグインがインストールされていることが前提です。

    Args:
        citygml_path (str): 表示対象のCityGMLのパス。
        lod_preference (int): 表示するLODの指定。最も単純な場合は`0`、詳細な場合は`1`、全ての場合は`2`を指定。
                              デフォルトでは`0`を指定。
        semantic_parts (bool): 建物の壁面など地物を構成する要素ごとにレイヤを分ける場合は`True`、分けない場合は`False`を指定。
                              デフォルトは`False`を指定。

    Returns:
        Dict[str, Any]: {
            "command": str | None,  # 生成されたQGIS実行コマンド、またはNone
            "status": str,          # "ready" または "error"
            "message": str          # 状態メッセージまたはエラーメッセージ
        }
    """
    # 初回実行時のみQGISとの接続を初期化
    if not qgis_command._initialized:
        await qgis_command.initialize()

    # QGISのPythonコンソールで実行可能な1行コマンドを生成
    cmd = f"processing.runAndLoadResults(\"plateau_plugin:load_as_vector\", {{'INPUT': '{citygml_path}', 'LOD_PREFERENCE': {lod_preference}, 'SEMANTIC_PARTS': {str(semantic_parts)}, 'FORCE_2D': False, 'APPEND_MODE': True, 'CRS': QgsCoordinateReferenceSystem('EPSG:6668')}})"

    return {
        "command": cmd,
        "status": "ready",
        "message": "QGISコマンドを生成しました。QGISが起動していることを確認してから実行してください。"
        if qgis_command.is_available() else
        "QGISコマンドを生成しましたが、QGISとの接続が確認できていません。QGISを起動し、PLATEAU QGISプラグインが有効になっていることを確認してください。"
    }


async def _extract_gml_files_flat(zip_path: str) -> Dict[str, Any]:
    """
    ZIPファイルからGMLファイルのみを抽出し、フラット構造で配置する内部ヘルパー関数。

    Args:
        zip_path (str): 展開対象のZIPファイルパス。

    Returns:
        Dict[str, Any]: 展開結果の詳細情報
    """
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"ZIPファイルが見つかりません: {zip_path}")

    # ZIPファイル名から展開先ディレクトリ名を生成
    zip_dir = os.path.dirname(zip_path)
    zip_filename = os.path.basename(zip_path)
    zip_name_without_ext = os.path.splitext(zip_filename)[0]
    extract_dir = os.path.join(zip_dir, f"extract_{zip_name_without_ext}")

    logger.info(f"ZIPファイル展開中: {zip_path}")
    logger.info(f"展開先ディレクトリ: {extract_dir}")

    # 既存の展開ディレクトリがある場合は削除
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)

    os.makedirs(extract_dir, exist_ok=True)

    gml_files = []
    total_extracted = 0

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # ZIP内の全ファイルを取得
            all_files = zip_ref.namelist()

            for file_path in all_files:
                # ディレクトリエントリはスキップ
                if file_path.endswith('/'):
                    continue

                # ファイル名のみを取得（パス情報を除去）
                file_name = os.path.basename(file_path)

                # .gmlファイルのみを対象とする
                if file_name.lower().endswith('.gml'):
                    # フラット構造で配置（元のディレクトリ構造は無視）
                    target_path = os.path.join(extract_dir, file_name)
                    
                    # 同名ファイルがある場合は連番を付与
                    counter = 1
                    original_target_path = target_path
                    while os.path.exists(target_path):
                        name, ext = os.path.splitext(original_target_path)
                        target_path = f"{name}_{counter}{ext}"
                        counter += 1

                    # ファイルを抽出
                    with zip_ref.open(file_path) as source, open(target_path, 'wb') as target:
                        shutil.copyfileobj(source, target)

                    gml_files.append(target_path)
                    total_extracted += 1
                    logger.debug(f"  抽出: {file_name}")

        logger.info(f"展開完了: {total_extracted}個のGMLファイルを抽出しました")

        # 展開結果を返す
        return {
            "extract_dir": extract_dir,
            "gml_files": gml_files,
            "total_files": total_extracted,
            "zip_filename": zip_filename,
            "success": True
        }

    except Exception as e:
        error_msg = f"ZIPファイル展開エラー: {e}"
        logger.error(error_msg)
        # エラー時は作成したディレクトリを削除
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        raise RuntimeError(error_msg)


def main():
    # stdio経由でMCPサーバーを起動
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
