import html
import json
import os
import sys
import uuid
import webbrowser
from datetime import datetime
from typing import Dict, Any, List, Union
from urllib.parse import urljoin

import requests
import yaml
from deepdiff import DeepDiff
from deepdiff.helper import SetOrdered


class TestResult:
    """Resultado de um teste individual"""
    def __init__(self, test_name: str):
        self.test_name = test_name
        self.success = False
        self.status_code = None
        self.response_data = None
        self.response_headers = None
        self.error_message = None
        self.execution_time = 0.0
        self.timestamp = datetime.now().isoformat()
        self.request_details = {}
        self.response_details = {}
        self.validation_details = {}


class ComparisonResult:
    """Resultado de uma comparação entre endpoints"""
    def __init__(self, comparison_name: str):
        self.comparison_name = comparison_name
        self.success = False
        self.timestamp = datetime.now().isoformat()
        self.endpoints_results = []
        self.comparison_details = {
            'status_match': False,
            'body_match': False,
            'differences': None,
            'ignored_fields': []
        }
        self.error_message = None


class APIComparator:
    """API Comparator - Compare and validate API endpoints with visual diff reporting"""
    
    def __init__(self, config_file: str = "api_comparator_config.yaml"):
        self.config_file = config_file
        self.config = self._load_config()
        self.results: List[TestResult] = []
        self.comparison_results: List[ComparisonResult] = []
        self.session = requests.Session()
        self.variables = {}
        self._setup_session()
    
    def _load_config(self) -> Dict[str, Any]:
        """Carrega a configuração do arquivo YAML"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Erro: Arquivo {self.config_file} não encontrado!")
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"Erro ao ler YAML: {e}")
            sys.exit(1)
    
    def _setup_session(self):
        """Configura a sessão HTTP com headers globais"""
        config = self.config.get('config', {})
        
        # Headers globais
        global_headers = config.get('headers', {})
        self.session.headers.update(global_headers)
        
        # Variáveis globais
        self.variables = config.get('variables', {})
        
        # Base URLs
        self.base_url = config.get('base_url', 'http://localhost:8080')
        self.base_url_comparison = config.get('base_url_comparison', None)
        self.timeout = config.get('timeout', 30)
    
    def _replace_variables(self, text: Union[str, Dict, List], local_uuid = None) -> Union[str, Dict, List]:
        """Substitui variáveis no formato {{variavel}} pelos valores"""
        if isinstance(text, str):
            # Substituir {{uuid}} por um novo UUID
            if '{{uuid}}' in text:
                if not local_uuid:
                    text = text.replace('{{uuid}}', str(uuid.uuid4()))
                else:
                    text = text.replace('{{uuid}}', local_uuid)
            
            # Substituir outras variáveis
            for key, value in self.variables.items():
                placeholder = f"{{{{{key}}}}}"
                if placeholder in text:
                    text = text.replace(placeholder, str(value))
            
            return text
        
        elif isinstance(text, dict):
            return {k: self._replace_variables(v, local_uuid) for k, v in text.items()}
        
        elif isinstance(text, list):
            return [self._replace_variables(item, local_uuid) for item in text]
        
        return text
    
    def _build_url(self, path: str, path_params: Dict[str, str] = None) -> str:
        """Constrói a URL completa com parâmetros de caminho"""
        # Substituir variáveis no path
        path = self._replace_variables(path)
        
        # Substituir parâmetros de caminho
        if path_params:
            for key, value in path_params.items():
                placeholder = f"{{{key}}}"
                path = path.replace(placeholder, str(self._replace_variables(value)))
        
        # Construir URL completa
        return urljoin(self.base_url, path)
    
    def _validate_response(self, response: requests.Response, expected: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
        """Valida a resposta contra as expectativas e retorna detalhes da validação"""
        validation_details = {
            'validations_passed': [],
            'validations_failed': [],
            'overall_success': True
        }
        
        if not expected:
            validation_details['validations_passed'].append("Nenhuma validação configurada - teste aprovado")
            return True, validation_details
        
        # Validar status code
        if 'status_code' in expected:
            expected_status = expected['status_code']
            actual_status = response.status_code
            if actual_status == expected_status:
                validation_details['validations_passed'].append(f"Status code: {actual_status} (esperado: {expected_status})")
            else:
                validation_details['validations_failed'].append(f"Status code: {actual_status} (esperado: {expected_status})")
                validation_details['overall_success'] = False
        
        # Validar headers
        if 'headers' in expected:
            for header, expected_value in expected['headers'].items():
                actual_value = response.headers.get(header, '')
                if expected_value.lower() in actual_value.lower():
                    validation_details['validations_passed'].append(f"Header '{header}': contém '{expected_value}'")
                else:
                    validation_details['validations_failed'].append(f"Header '{header}': '{actual_value}' não contém '{expected_value}'")
                    validation_details['overall_success'] = False
        
        # Validar corpo da resposta
        if 'body' in expected:
            try:
                response_json = response.json()
                
                # Verificar se contém campos específicos
                if 'contains' in expected['body']:
                    for field in expected['body']['contains']:
                        if field in str(response_json):
                            validation_details['validations_passed'].append(f"Body contém: '{field}'")
                        else:
                            validation_details['validations_failed'].append(f"Body não contém: '{field}'")
                            validation_details['overall_success'] = False
                
                # Verificar valores exatos
                if 'exact' in expected['body']:
                    for key, expected_value in expected['body']['exact'].items():
                        actual_value = response_json.get(key)
                        if actual_value == expected_value:
                            validation_details['validations_passed'].append(f"Body['{key}']: {actual_value} (esperado: {expected_value})")
                        else:
                            validation_details['validations_failed'].append(f"Body['{key}']: {actual_value} (esperado: {expected_value})")
                            validation_details['overall_success'] = False
                
            except json.JSONDecodeError:
                validation_details['validations_failed'].append("Erro: esperava JSON mas a resposta não é um JSON válido")
                validation_details['overall_success'] = False
        
        return validation_details['overall_success'], validation_details
    
    def _execute_request(self, test_config: Dict[str, Any]) -> requests.Response:
        """Executa a requisição HTTP"""
        request_config = test_config['request']
        local_uuid =  test_config['local_uuid'] if 'local_uuid' in test_config else None
        
        # Preparar componentes da requisição
        method = request_config['method'].upper()
        # verifica se há comparison_path caso haja substitui usa na requisicao
        # caso não usao path
        if request_config.get("comparison_path",False):
            path = request_config.get("comparison_path","/")
        else:
            path = request_config.get('path', '/')

        path_params = self._replace_variables(request_config.get('path_params', {}), local_uuid)
        
        # Construir URL
        url = self._build_url(path, path_params)
        
        # Headers específicos do teste
        headers = self.session.headers.copy()
        if 'headers' in request_config:
            test_headers = self._replace_variables(request_config['headers'], local_uuid)
            headers.update(test_headers)
        
        # Query parameters
        params = self._replace_variables(request_config.get('query_params', {}), local_uuid)
        
        # Body da requisição
        json_body = None
        data = None
        if 'body' in request_config:
            body = self._replace_variables(request_config['body'], local_uuid)
            if headers.get('Content-Type', '').lower() == 'application/json':
                json_body = body
            else:
                data = body
        
        # Executar requisição
        response = self.session.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_body,
            data=data,
            timeout=self.timeout
        )
        
        return response
    
    def _execute_test(self, test: Dict[str, Any]) -> TestResult:
        """Executa um teste individual"""
        result = TestResult(test['name'])
        
        try:
            # Executar requisição
            start_time = datetime.now()
            response = self._execute_request(test)
            end_time = datetime.now()
            
            result.execution_time = (end_time - start_time).total_seconds()
            result.status_code = response.status_code
            result.response_headers = dict(response.headers)
            
            # Armazenar detalhes da requisição
            result.request_details = {
                'method': test['request']['method'],
                'url': response.request.url,
                'headers': dict(response.request.headers)
            }
            
            # Adicionar body da requisição se existir
            if response.request.body:
                try:
                    # Tentar decodificar como JSON se possível
                    if isinstance(response.request.body, bytes):
                        body_text = response.request.body.decode('utf-8')
                        try:
                            result.request_details['body'] = json.loads(body_text)
                        except json.JSONDecodeError:
                            result.request_details['body'] = body_text
                    else:
                        result.request_details['body'] = response.request.body
                except Exception:
                    result.request_details['body'] = str(response.request.body)
            else:
                result.request_details['body'] = None
            
            # Tentar parsear resposta como JSON
            try:
                result.response_data = response.json()
            except json.JSONDecodeError:
                result.response_data = response.text
            
            # Armazenar detalhes da resposta
            result.response_details = {
                'status_code': response.status_code,
                'headers': result.response_headers,
                'body': result.response_data
            }
            
            # Validar resposta
            expected = test.get('expected', {})
            result.success, result.validation_details = self._validate_response(response, expected)
            
            # Salvar arquivo se configurado
            if expected.get('save_response_to') and response.content:
                with open(expected['save_response_to'], 'wb') as f:
                    f.write(response.content)
            
        except requests.exceptions.RequestException as e:
            result.success = False
            result.error_message = f"Erro na requisição: {str(e)}"
        except Exception as e:
            result.success = False
            result.error_message = f"Erro: {str(e)}"
        
        return result
    
    def _execute_comparison(self, comparison: Dict[str, Any]) -> ComparisonResult:
        """Executa uma comparação entre endpoints"""
        result = ComparisonResult(comparison['name'])
        
        try:
            # Se há apenas um request e duas base_urls configuradas, usar ambas
            local_uuid : str = str(uuid.uuid4())
            if 'request' in comparison and self.base_url_comparison:
                endpoints = [
                    {
                        'name': 'Host 1',
                        'request': comparison['request'],
                        'base_url': self.base_url,
                    },
                    {
                        'name': 'Host 2', 
                        'request': comparison['request'],
                        'base_url': self.base_url_comparison,
                    }
                ]
            else:
                endpoints = comparison.get('endpoints', [])
            
            if len(endpoints) < 2:
                result.error_message = "Comparação requer pelo menos 2 endpoints ou configuração base_url_comparison"
                return result
            
            # Executar requisições para todos os endpoints
            endpoint_responses = []
            for endpoint in endpoints:
                endpoint_name = endpoint.get('name', f'Endpoint {len(endpoint_responses) + 1}')
                
                # Preparar configuração do teste
                test_config = {
                    'name': endpoint_name,
                    'request': endpoint['request'],
                    'local_uuid': local_uuid,
                }
                
                # Usar base_url específica se fornecida
                if 'base_url' in endpoint:
                    original_base_url = self.base_url
                    self.base_url = endpoint['base_url']
                
                try:
                    response = self._execute_request(test_config)
                    
                    # Capturar base_url usada
                    used_base_url = endpoint.get('base_url', self.base_url)
                    
                    response_data = {
                        'name': endpoint_name,
                        'status_code': response.status_code,
                        'headers': dict(response.headers),
                        'body': None,
                        'raw_response': response,
                        'request_details': {
                            'base_url': used_base_url,
                            'method': endpoint['request']['method'].upper(),
                            'path': endpoint['request'].get('path', '/'),
                            'full_url': response.request.url,
                            'headers': dict(response.request.headers),
                            'query_params': dict(response.request.query_params) if hasattr(response.request, 'query_params') else {},
                            'body': None
                        }
                    }
                    
                    # Capturar body da requisição
                    if response.request.body:
                        try:
                            if isinstance(response.request.body, bytes):
                                body_text = response.request.body.decode('utf-8')
                                try:
                                    response_data['request_details']['body'] = json.loads(body_text)
                                except json.JSONDecodeError:
                                    response_data['request_details']['body'] = body_text
                            else:
                                response_data['request_details']['body'] = response.request.body
                        except Exception:
                            response_data['request_details']['body'] = str(response.request.body)
                    
                    # Adicionar query params se existirem no endpoint
                    if 'params' in endpoint['request']:
                        response_data['request_details']['configured_params'] = self._replace_variables(endpoint['request']['params'])
                    
                    # Tentar parsear JSON da resposta
                    try:
                        response_data['body'] = response.json()
                    except json.JSONDecodeError:
                        response_data['body'] = response.text
                    
                    endpoint_responses.append(response_data)
                    
                finally:
                    # Restaurar base_url original se foi alterada
                    if 'base_url' in endpoint:
                        self.base_url = original_base_url
            
            result.endpoints_results = endpoint_responses
            
            # Comparar respostas
            validation = comparison.get('validation', {})
            result.comparison_details['ignored_fields'] = validation.get('ignore_fields', [])
            
            # Comparar status codes
            if validation.get('compare_status', True):
                status_codes = [r['status_code'] for r in endpoint_responses]
                result.comparison_details['status_match'] = all(s == status_codes[0] for s in status_codes)
            else:
                result.comparison_details['status_match'] = True
            
            # Comparar bodies
            if validation.get('compare_body', True):
                bodies = [r['body'] for r in endpoint_responses]
                
                # Se todos são JSON, usar DeepDiff
                if all(isinstance(b, dict) or isinstance(b, list) for b in bodies):
                    # Comparar o primeiro com todos os outros
                    all_match = True
                    differences = []
                    
                    for i in range(1, len(bodies)):
                        diff = DeepDiff(
                            bodies[0], 
                            bodies[i],
                            ignore_order=True,
                            exclude_paths=result.comparison_details['ignored_fields']
                        )
                        
                        if diff:
                            all_match = False
                            differences.append({
                                'endpoint1': endpoint_responses[0]['name'],
                                'endpoint2': endpoint_responses[i]['name'],
                                'diff': diff.to_dict()
                            })
                    
                    result.comparison_details['body_match'] = all_match
                    result.comparison_details['differences'] = differences
                else:
                    # Comparação simples de strings
                    result.comparison_details['body_match'] = all(b == bodies[0] for b in bodies)
                    if not result.comparison_details['body_match']:
                        result.comparison_details['differences'] = "Conteúdo diferente (não-JSON)"
            else:
                result.comparison_details['body_match'] = True
            
            # Determinar sucesso geral
            result.success = (
                result.comparison_details['status_match'] and 
                result.comparison_details['body_match']
            )
            
        except Exception as e:
            result.success = False
            result.error_message = f"Erro durante comparação: {str(e)}"
        
        return result
    
    def run_tests(self):
        """Executa todos os testes configurados"""
        tests = self.config.get('tests', [])
        comparisons = self.config.get('comparisons', [])
        report_config = self.config.get('report', {})
        verbose = report_config.get('verbose', True)
        stop_on_failure = report_config.get('stop_on_failure', False)
        
        # Executar testes normais
        if tests:
            print(f"\n{'='*60}")
            print(f"Executando {len([t for t in tests if t.get('enabled', True)])} testes de API")
            print(f"Base URL: {self.base_url}")
            print(f"{'='*60}\n")
            
            for test in tests:
                if not test.get('enabled', True):
                    print(f"⏭️  {test['name']} - DESABILITADO")
                    continue
                
                if verbose:
                    print(f"🧪 Executando: {test['name']}")
                    print(f"   Descrição: {test.get('description', 'N/A')}")
                    print(f"   Método: {test['request']['method']} {test['request']['path']}")
                
                result = self._execute_test(test)
                self.results.append(result)
                
                if result.success:
                    print(f"✅ {test['name']} - SUCESSO ({result.execution_time:.2f}s)")
                else:
                    print(f"❌ {test['name']} - FALHA (Status: {result.status_code})")
                    if verbose and result.error_message:
                        print(f"   Erro: {result.error_message}")
                
                # Mostrar detalhes da validação se verbose
                if verbose and result.validation_details:
                    if result.validation_details.get('validations_passed'):
                        for validation in result.validation_details['validations_passed']:
                            print(f"   ✅ {validation}")
                    if result.validation_details.get('validations_failed'):
                        for validation in result.validation_details['validations_failed']:
                            print(f"   ❌ {validation}")
                
                if verbose and result.request_details:
                    print(f"   URL: {result.request_details.get('url', 'N/A')}")
                
                # Mostrar response se configurado
                if report_config.get('show_response_in_console', False):
                    self._show_response_in_console(result, report_config)
                
                if stop_on_failure and not result.success:
                    print("\n⚠️  Parando execução devido a falha (stop_on_failure=true)")
                    break
        
        # Executar comparações
        if comparisons:
            print(f"\n{'='*60}")
            print(f"Executando {len([c for c in comparisons if c.get('enabled', True)])} comparações entre endpoints")
            print(f"{'='*60}\n")
            
            for comparison in comparisons:
                if not comparison.get('enabled', True):
                    print(f"⏭️  {comparison['name']} - DESABILITADO")
                    continue
                
                result = self._execute_comparison(comparison)
                self.comparison_results.append(result)
                
                if result.success:
                    print(f"✅ {comparison['name']} - ENDPOINTS IDÊNTICOS")
                else:
                    print(f"❌ {comparison['name']} - ENDPOINTS DIFERENTES")
                    if result.error_message:
                        print(f"   Erro: {result.error_message}")
                    else:
                        if not result.comparison_details['status_match']:
                            print(f"   ❌ Status codes diferentes")
                        if not result.comparison_details['body_match']:
                            print(f"   ❌ Conteúdo dos bodies diferentes")
        
        self._generate_report()
    
    def _show_response_in_console(self, result: TestResult, report_config: Dict[str, Any]):
        """Mostra o response no console de acordo com as configurações"""
        if not result.response_data:
            return
        
        format_json = report_config.get('format_json_response', True)
        max_length = report_config.get('max_response_display_length', 1000)
        
        print(f"   📄 Response (Status {result.status_code}):")
        
        try:
            # Se response_data é um dict (JSON), formatá-lo
            if isinstance(result.response_data, dict) and format_json:
                response_text = json.dumps(self._make_serializable(result.response_data), indent=2, ensure_ascii=False)
            else:
                response_text = str(result.response_data)
            
            # Limitar tamanho se configurado
            if max_length > 0 and len(response_text) > max_length:
                response_text = response_text[:max_length] + "... [truncado]"
            
            # Indentar todas as linhas para ficar alinhado
            lines = response_text.split('\n')
            for line in lines:
                print(f"      {line}")
                
        except Exception as e:
            print(f"      Erro ao formatar response: {e}")
        
        print()  # Linha em branco

    def _make_serializable(self, obj):
        if isinstance(obj, SetOrdered):
            return list(obj)
        elif isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_serializable(item) for item in obj]
        return obj

    def _generate_report(self):
        """Gera relatório dos testes"""
        report_config = self.config.get('report', {})
        
        total_tests = len(self.results)
        successful_tests = sum(1 for r in self.results if r.success)
        failed_tests = total_tests - successful_tests
        
        print(f"\n{'='*60}")
        print("RESUMO DOS TESTES")
        print(f"{'='*60}")
        print(f"Total de testes: {total_tests}")
        print(f"✅ Sucessos: {successful_tests}")
        print(f"❌ Falhas: {failed_tests}")
        if total_tests > 0:
            print(f"Taxa de sucesso: {(successful_tests/total_tests*100):.1f}%")
        
        if failed_tests > 0:
            print("\nTestes que falharam:")
            for result in self.results:
                if not result.success:
                    print(f"  - {result.test_name}: {result.error_message or f'Status {result.status_code}'}")
        
        # Resumo das comparações
        if self.comparison_results:
            total_comparisons = len(self.comparison_results)
            successful_comparisons = sum(1 for c in self.comparison_results if c.success)
            failed_comparisons = total_comparisons - successful_comparisons
            
            print(f"\n{'='*60}")
            print("RESUMO DAS COMPARAÇÕES")
            print(f"{'='*60}")
            print(f"Total de comparações: {total_comparisons}")
            print(f"✅ Idênticas: {successful_comparisons}")
            print(f"❌ Diferentes: {failed_comparisons}")
            
            if failed_comparisons > 0:
                print("\nComparações com diferenças:")
                for result in self.comparison_results:
                    if not result.success:
                        print(f"  - {result.comparison_name}")
        
        # Salvar resultados se configurado
        if report_config.get('save_results', True):
            output_file = report_config.get('output_file', 'test_results.json')
            self._save_results(output_file, report_config)
            print(f"\n📄 Resultados salvos em: {output_file}")
            
            # Gerar relatório HTML de comparações se houver comparações
            if self.comparison_results:
                html_file = report_config.get('comparison_report', 'comparison_report.html')
                try:
                    self._generate_html_comparison_report_simple(html_file)

                    webbrowser.open(os.path.abspath(html_file))
                except Exception as e:
                    print(f"Erro ao gerar HTML: {e}")
                print(f"📄 Relatório HTML de comparações salvo em: {html_file}")
    
    def _save_results(self, filename: str, report_config: Dict[str, Any]):
        """Salva os resultados em arquivo JSON"""
        include_request = report_config.get('include_request_details', True)
        include_response = report_config.get('include_response_details', True)
        
        results_data = {
            'timestamp': datetime.now().isoformat(),
            'config': {
                'base_url': self.base_url,
                'timeout': self.timeout,
                'config_file': self.config_file
            },
            'summary': {
                'tests': {
                    'total': len(self.results),
                    'success': sum(1 for r in self.results if r.success),
                    'failed': sum(1 for r in self.results if not r.success)
                },
                'comparisons': {
                    'total': len(self.comparison_results),
                    'identical': sum(1 for c in self.comparison_results if c.success),
                    'different': sum(1 for c in self.comparison_results if not c.success)
                }
            },
            'results': [],
            'comparisons': []
        }
        
        for result in self.results:
            test_result = {
                'test_name': result.test_name,
                'success': result.success,
                'status_code': result.status_code,
                'execution_time': result.execution_time,
                'timestamp': result.timestamp,
                'error_message': result.error_message,
                'validation_details': result.validation_details
            }
            
            if include_request:
                test_result['request'] = result.request_details
            
            if include_response:
                test_result['response'] = result.response_details
            
            results_data['results'].append(test_result)
        
        # Adicionar resultados das comparações
        for comparison in self.comparison_results:
            comparison_result = {
                'comparison_name': comparison.comparison_name,
                'success': comparison.success,
                'timestamp': comparison.timestamp,
                'error_message': comparison.error_message,
                'comparison_details': comparison.comparison_details,
                'endpoints_results': []
            }
            
            # Incluir detalhes de cada endpoint (sem o raw_response)
            for endpoint in comparison.endpoints_results:
                endpoint_data = {
                    'name': endpoint['name'],
                    'status_code': endpoint['status_code'],
                    'headers': endpoint['headers'],
                    'body': endpoint['body']
                }
                comparison_result['endpoints_results'].append(endpoint_data)
            
            results_data['comparisons'].append(comparison_result)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self._make_serializable(results_data), f, indent=2, ensure_ascii=False)
    
    def _generate_html_comparison_report_simple(self, filename: str):
        """Gera relatório HTML com diferenças visuais detalhadas entre endpoints"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Comparação de Endpoints</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 20px;
            background-color: #f8f9fa;
        }
        h1 {
            color: #2c3e50;
            text-align: center;
            margin-bottom: 30px;
        }
        h2 {
            color: #34495e;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
            margin-top: 40px;
        }
        h3 {
            margin-top: 0;
            font-weight: bold;
        }
        .comparison-container {
            display: flex;
            gap: 20px;
            margin-bottom: 30px;
        }
        .endpoint-container {
            flex: 1;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            background-color: white;
            border: 2px solid #e0e0e0;
        }
        .status-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 14px;
            margin-bottom: 10px;
        }
        .status-2xx { background-color: #d4edda; color: #155724; }
        .status-4xx { background-color: #f8d7da; color: #721c24; }
        .status-5xx { background-color: #f8d7da; color: #721c24; }
        .payload {
            border-radius: 6px;
            padding: 15px;
            overflow: auto;
            max-height: 400px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 13px;
            line-height: 1.6;
            white-space: pre;
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
        }
        .diff-line {
            margin: 0;
            padding: 2px 5px;
            border-left: 3px solid transparent;
        }
        .diff-removed {
            background-color: #ffeaea;
            border-left-color: #f56565;
            color: #c53030;
        }
        .diff-added {
            background-color: #f0fff4;
            border-left-color: #48bb78;
            color: #2d7d32;
        }
        .diff-modified {
            background-color: #fff8dc;
            border-left-color: #ed8936;
            color: #c05621;
        }
        .diff-unchanged {
            color: #718096;
        }
        .char-removed {
            background-color: #fed7d7;
            text-decoration: line-through;
        }
        .char-added {
            background-color: #c6f6d5;
            font-weight: bold;
        }
        .char-modified {
            background-color: #faf089;
            font-weight: bold;
        }
        .differences {
            background-color: #fff5f5;
            border: 1px solid #fed7d7;
            border-radius: 8px;
            padding: 20px;
            margin-top: 20px;
        }
        .differences h3 {
            color: #c53030;
            margin-top: 0;
        }
        .legend {
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
            font-size: 12px;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 5px;
        }
        .legend-color {
            width: 15px;
            height: 15px;
            border-radius: 3px;
        }
        .result-banner {
            text-align: center;
            padding: 15px;
            margin: 20px 0;
            border-radius: 8px;
            font-size: 18px;
            font-weight: bold;
        }
        .result-success {
            background-color: #d4edda;
            color: #155724;
            border: 2px solid #c3e6cb;
        }
        .result-failure {
            background-color: #f8d7da;
            color: #721c24;
            border: 2px solid #f5c6cb;
        }
    </style>
</head>
<body>''')
            
            f.write(f'<h1>🔍 Relatório de Comparação de Endpoints</h1>')
            f.write(f'<p style="text-align: center; color: #666; margin-bottom: 40px;">Gerado em: {datetime.now().strftime("%d/%m/%Y às %H:%M:%S")}</p>')
            
            # Legenda
            f.write('''<div class="legend">
                <div class="legend-item">
                    <div class="legend-color" style="background-color: #ffeaea; border: 1px solid #f56565;"></div>
                    <span>Removido</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background-color: #f0fff4; border: 1px solid #48bb78;"></div>
                    <span>Adicionado</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background-color: #fff8dc; border: 1px solid #ed8936;"></div>
                    <span>Modificado</span>
                </div>
            </div>''')
            
            for result in self.comparison_results:
                f.write(f'<h2>📊 {html.escape(result.comparison_name)}</h2>')
                
                # Banner de resultado (sucesso ou falha)
                if result.success:
                    f.write(f'<div class="result-banner result-success">✅ COMPARAÇÃO IDÊNTICA - SUCESSO</div>')
                else:
                    f.write(f'<div class="result-banner result-failure">❌ COMPARAÇÃO DIFERENTE - FALHA</div>')
                
                # Gerar diff visual se houver exatamente 2 endpoints
                if len(result.endpoints_results) == 2:
                    endpoint1 = result.endpoints_results[0]
                    endpoint2 = result.endpoints_results[1]
                    
                    f.write('<div class="comparison-container">')
                    
                    # Gerar conteúdo formatado para ambos endpoints
                    content1 = self._format_json_content(endpoint1['body'])
                    content2 = self._format_json_content(endpoint2['body'])
                    
                    # Gerar diff visual
                    diff_html1, diff_html2 = self._generate_visual_diff(content1, content2, endpoint1['name'], endpoint2['name'])
                    
                    # Endpoint 1
                    f.write('<div class="endpoint-container">')
                    f.write(f'<h3>🌐 {html.escape(endpoint1["name"])}</h3>')
                    status_class = "status-2xx" if 200 <= endpoint1["status_code"] < 300 else "status-4xx" if 400 <= endpoint1["status_code"] < 500 else "status-5xx"
                    f.write(f'<div class="status-badge {status_class}">Status: {endpoint1["status_code"]}</div>')
                    
                    # Detalhes do request
                    if 'request_details' in endpoint1:
                        req = endpoint1['request_details']
                        f.write('<div style="background-color: #f0f8ff; border: 1px solid #cce7ff; border-radius: 4px; padding: 10px; margin-bottom: 10px; font-size: 12px;">')
                        f.write(f'<strong>🔗 Base URL:</strong> {html.escape(req.get("base_url", "N/A"))}<br>')
                        f.write(f'<strong>📍 Request:</strong> {html.escape(req.get("method", ""))} {html.escape(req.get("path", ""))}<br>')
                        f.write(f'<strong>🌐 Full URL:</strong> {html.escape(req.get("full_url", ""))}<br>')
                        if req.get('configured_params'):
                            f.write(f'<strong>🔍 Query Params:</strong> {html.escape(str(req["configured_params"]))}<br>')
                        if req.get('body'):
                            f.write(f'<strong>📦 Body:</strong> {html.escape(str(req["body"]))}<br>')
                        f.write('</div>')
                    
                    f.write('<div class="payload">')
                    f.write(diff_html1)
                    f.write('</div></div>')
                    
                    # Endpoint 2
                    f.write('<div class="endpoint-container">')
                    f.write(f'<h3>🌐 {html.escape(endpoint2["name"])}</h3>')
                    status_class = "status-2xx" if 200 <= endpoint2["status_code"] < 300 else "status-4xx" if 400 <= endpoint2["status_code"] < 500 else "status-5xx"
                    f.write(f'<div class="status-badge {status_class}">Status: {endpoint2["status_code"]}</div>')
                    
                    # Detalhes do request
                    if 'request_details' in endpoint2:
                        req = endpoint2['request_details']
                        f.write('<div style="background-color: #f0f8ff; border: 1px solid #cce7ff; border-radius: 4px; padding: 10px; margin-bottom: 10px; font-size: 12px;">')
                        f.write(f'<strong>🔗 Base URL:</strong> {html.escape(req.get("base_url", "N/A"))}<br>')
                        f.write(f'<strong>📍 Request:</strong> {html.escape(req.get("method", ""))} {html.escape(req.get("path", ""))}<br>')
                        f.write(f'<strong>🌐 Full URL:</strong> {html.escape(req.get("full_url", ""))}<br>')
                        if req.get('configured_params'):
                            f.write(f'<strong>🔍 Query Params:</strong> {html.escape(str(req["configured_params"]))}<br>')
                        if req.get('body'):
                            f.write(f'<strong>📦 Body:</strong> {html.escape(str(req["body"]))}<br>')
                        f.write('</div>')
                    
                    f.write('<div class="payload">')
                    f.write(diff_html2)
                    f.write('</div></div>')
                    
                    f.write('</div>')
                else:
                    # Fallback para mais de 2 endpoints (formato original)
                    f.write('<div class="comparison-container">')
                    for endpoint in result.endpoints_results:
                        f.write('<div class="endpoint-container">')
                        f.write(f'<h3>🌐 {html.escape(endpoint["name"])}</h3>')
                        status_class = "status-2xx" if 200 <= endpoint["status_code"] < 300 else "status-4xx" if 400 <= endpoint["status_code"] < 500 else "status-5xx"
                        f.write(f'<div class="status-badge {status_class}">Status: {endpoint["status_code"]}</div>')
                        f.write('<div class="payload">')
                        content = self._format_json_content(endpoint['body'])
                        f.write(html.escape(content))
                        f.write('</div></div>')
                    f.write('</div>')
            
            f.write('</body></html>')
    
    def _format_json_content(self, body):
        """Formata o conteúdo JSON para exibição"""
        if isinstance(body, (dict, list)):
            return json.dumps(body, indent=2, ensure_ascii=False)
        else:
            return str(body)
    
    def _generate_visual_diff(self, content1: str, content2: str, name1: str, name2: str):
        """Gera diff visual linha por linha entre dois conteúdos"""
        import difflib
        
        lines1 = content1.splitlines()
        lines2 = content2.splitlines()
        
        # Usar difflib para gerar diff
        diff = list(difflib.unified_diff(lines1, lines2, lineterm='', n=1000))
        
        # Processar diff para gerar HTML
        html1_lines = []
        html2_lines = []
        
        # Mapear linhas originais para o diff
        matcher = difflib.SequenceMatcher(None, lines1, lines2)
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                # Linhas iguais
                for k in range(i1, i2):
                    html1_lines.append(f'<div class="diff-line diff-unchanged">{html.escape(lines1[k])}</div>')
                for k in range(j1, j2):
                    html2_lines.append(f'<div class="diff-line diff-unchanged">{html.escape(lines2[k])}</div>')
            elif tag == 'delete':
                # Linhas removidas (apenas em content1)
                for k in range(i1, i2):
                    html1_lines.append(f'<div class="diff-line diff-removed">{html.escape(lines1[k])}</div>')
            elif tag == 'insert':
                # Linhas adicionadas (apenas em content2)
                for k in range(j1, j2):
                    html2_lines.append(f'<div class="diff-line diff-added">{html.escape(lines2[k])}</div>')
            elif tag == 'replace':
                # Linhas modificadas
                for k in range(i1, i2):
                    line1 = lines1[k]
                    # Tentar encontrar linha correspondente para diff de caracteres
                    if k - i1 < j2 - j1:
                        line2 = lines2[j1 + (k - i1)]
                        char_diff1, char_diff2 = self._generate_char_diff(line1, line2)
                        html1_lines.append(f'<div class="diff-line diff-modified">{char_diff1}</div>')
                    else:
                        html1_lines.append(f'<div class="diff-line diff-removed">{html.escape(line1)}</div>')
                
                for k in range(j1, j2):
                    line2 = lines2[k]
                    if k - j1 < i2 - i1:
                        line1 = lines1[i1 + (k - j1)]
                        char_diff1, char_diff2 = self._generate_char_diff(line1, line2)
                        html2_lines.append(f'<div class="diff-line diff-modified">{char_diff2}</div>')
                    else:
                        html2_lines.append(f'<div class="diff-line diff-added">{html.escape(line2)}</div>')
        
        # Equalizar o número de linhas
        while len(html1_lines) < len(html2_lines):
            html1_lines.append('<div class="diff-line"></div>')
        while len(html2_lines) < len(html1_lines):
            html2_lines.append('<div class="diff-line"></div>')
        
        return '\n'.join(html1_lines), '\n'.join(html2_lines)
    
    def _generate_char_diff(self, line1: str, line2: str):
        """Gera diff a nível de caracteres entre duas linhas"""
        import difflib
        
        matcher = difflib.SequenceMatcher(None, line1, line2)
        
        result1 = []
        result2 = []
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                text = html.escape(line1[i1:i2])
                result1.append(text)
                result2.append(text)
            elif tag == 'delete':
                result1.append(f'<span class="char-removed">{html.escape(line1[i1:i2])}</span>')
            elif tag == 'insert':
                result2.append(f'<span class="char-added">{html.escape(line2[j1:j2])}</span>')
            elif tag == 'replace':
                result1.append(f'<span class="char-modified">{html.escape(line1[i1:i2])}</span>')
                result2.append(f'<span class="char-modified">{html.escape(line2[j1:j2])}</span>')
        
        return ''.join(result1), ''.join(result2)
    
    def _generate_html_comparison_report(self, filename: str):
        """Gera relatório HTML com as diferenças visuais entre endpoints"""
        html_content = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Relatório de Comparação de Endpoints</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1, h2, h3 {
            color: #2c3e50;
        }
        .summary {
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 30px;
        }
        .comparison {
            margin-bottom: 40px;
            border: 1px solid #e0e0e0;
            border-radius: 5px;
            overflow: hidden;
        }
        .comparison-header {
            background-color: #f8f9fa;
            padding: 15px;
            border-bottom: 1px solid #e0e0e0;
        }
        .comparison-header.success {
            background-color: #d4edda;
            border-color: #c3e6cb;
        }
        .comparison-header.failure {
            background-color: #f8d7da;
            border-color: #f5c6cb;
        }
        .endpoints {
            display: flex;
            gap: 20px;
            padding: 20px;
        }
        .endpoint {
            flex: 1;
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
        }
        .endpoint h4 {
            margin-top: 0;
            color: #495057;
        }
        .status-code {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 3px;
            font-weight: bold;
            font-size: 14px;
        }
        .status-2xx { background-color: #d4edda; color: #155724; }
        .status-3xx { background-color: #fff3cd; color: #856404; }
        .status-4xx { background-color: #f8d7da; color: #721c24; }
        .status-5xx { background-color: #f8d7da; color: #721c24; }
        .differences {
            margin: 20px;
            padding: 20px;
            background-color: #fff5f5;
            border: 1px solid #ffdddd;
            border-radius: 5px;
        }
        .diff-item {
            margin-bottom: 15px;
            padding: 10px;
            background-color: white;
            border: 1px solid #e0e0e0;
            border-radius: 3px;
        }
        .diff-type {
            font-weight: bold;
            color: #d73a49;
            margin-bottom: 5px;
        }
        .diff-detail {
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 13px;
            background-color: #f6f8fa;
            padding: 8px;
            border-radius: 3px;
            overflow-x: auto;
        }
        .json-content {
            background-color: #f6f8fa;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            max-height: 400px;
            overflow-y: auto;
        }
        pre {
            margin: 0;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .timestamp {
            color: #6c757d;
            font-size: 14px;
        }
        .badge {
            display: inline-block;
            padding: 4px 8px;
            font-size: 12px;
            font-weight: bold;
            border-radius: 3px;
            text-transform: uppercase;
        }
        .badge-success { background-color: #28a745; color: white; }
        .badge-danger { background-color: #dc3545; color: white; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Relatório de Comparação de Endpoints</h1>
        <p class="timestamp">Gerado em: {timestamp}</p>
        
        <div class="summary">
            <h2>Resumo</h2>
            <p>Total de comparações: <strong>{total}</strong></p>
            <p>Idênticas: <strong style="color: #28a745;">{identical}</strong></p>
            <p>Diferentes: <strong style="color: #dc3545;">{different}</strong></p>
        </div>
        
        {comparisons}
    </div>
</body>
</html>
"""
        
        comparisons_html = ""
        
        for result in self.comparison_results:
            if not result.success:
                comparison_html = f"""
        <div class="comparison">
            <div class="comparison-header failure">
                <h3>{html.escape(result.comparison_name)} <span class="badge badge-danger">DIFERENTES</span></h3>
            </div>
            
            <div class="endpoints">
"""
                
                # Adicionar informações de cada endpoint
                for endpoint in result.endpoints_results:
                    status_class = self._get_status_class(endpoint['status_code'])
                    
                    # Formatar body para exibição
                    body_content = ""
                    if isinstance(endpoint['body'], (dict, list)):
                        body_content = json.dumps(endpoint['body'], indent=2, ensure_ascii=False)
                    else:
                        body_content = str(endpoint['body'])
                    
                    comparison_html += f"""
                <div class="endpoint">
                    <h4>{html.escape(endpoint['name'])}</h4>
                    <p>Status: <span class="status-code {status_class}">{endpoint['status_code']}</span></p>
                    <div class="json-content">
                        <pre>{html.escape(body_content)}</pre>
                    </div>
                </div>
"""
                
                comparison_html += """
            </div>
"""
                
                # Adicionar diferenças se houver
                if result.comparison_details['differences'] and isinstance(result.comparison_details['differences'], list):
                    comparison_html += """
            <div class="differences">
                <h4>Diferenças Encontradas</h4>
"""
                    
                    for diff in result.comparison_details['differences']:
                        comparison_html += f"""
                <div class="diff-item">
                    <div class="diff-type">Entre {html.escape(diff['endpoint1'])} e {html.escape(diff['endpoint2'])}</div>
                    <div class="diff-detail">
                        <pre>{html.escape(json.dumps(diff['diff'], indent=2, ensure_ascii=False))}</pre>
                    </div>
                </div>
"""
                    
                    comparison_html += """
            </div>
"""
                
                comparison_html += """
        </div>
"""
                comparisons_html += comparison_html
        
        # Preencher template
        total = len(self.comparison_results)
        identical = sum(1 for c in self.comparison_results if c.success)
        different = total - identical
        
        html_final = html_content.format(
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            total=total,
            identical=identical,
            different=different,
            comparisons=comparisons_html
        )
        
        # Salvar arquivo
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_final)
    
    def _get_status_class(self, status_code: int) -> str:
        """Retorna a classe CSS baseada no status code"""
        if 200 <= status_code < 300:
            return "status-2xx"
        elif 300 <= status_code < 400:
            return "status-3xx"
        elif 400 <= status_code < 500:
            return "status-4xx"
        else:
            return "status-5xx"
    
    def cleanup(self):
        """Limpa recursos"""
        self.session.close()


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='API Comparator - Compare and validate API endpoints')
    parser.add_argument(
        '-c', '--config',
        default='api_comparator_config.yaml',
        help='YAML configuration file (default: api_comparator_config.yaml)'
    )
    
    args = parser.parse_args()
    
    comparator = APIComparator(args.config)
    
    try:
        comparator.run_tests()
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during test execution: {e}")
        raise e
    finally:
        comparator.cleanup()


if __name__ == "__main__":
    main()