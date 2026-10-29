# Домашняя работа 2: три реакции Kubernetes

## Данные студента

- ФИО: Котов Илья Евгеньевич
- Группа: ФТ-304
- ОС: Windows, amd64; кластер kind в Docker Desktop/WSL2
- Дата выполнения: 29.10.2026

## Приложение и клиент

Для домашней работы использовано приложение Python/Flask из первой работы. Добавлены `/ready`, `/live`, `/you-are-death`, `/not-ready` и `/ready-again`. Версия приложения задаётся при сборке образа и возвращается на `/`; APP_TOKEN выводится только как признак `set`, значение не раскрывается.

Основной сетевой вариант: `client → Service web → готовый Pod`. ConfigMap клиента задаёт адрес `web.homework-2.svc.cluster.local` и порт 80. Клиент работал в отдельном Pod и делал запрос каждые две секунды. В логах были HTTP 200 и разные имена Pod.

### Сборка образов

Из каталога `working/homework-2/app`:

```text
docker build --build-arg APP_VERSION=v1 -t localhost:5001/homework2-web:v1 .
docker push localhost:5001/homework2-web:v1
docker build --build-arg APP_VERSION=v2 -t localhost:5001/homework2-web:v2 .
docker push localhost:5001/homework2-web:v2
```

Из каталога `client`:

```text
docker build -t localhost:5001/client:v1 .
docker push localhost:5001/client:v1
```

Теги приложения: `localhost:5001/homework2-web:v1` и `localhost:5001/homework2-web:v2`. Push v1 завершился с digest `sha256:8817683edb35943a4702de9fc5d14cef02ea82b51cff9573336fede91babb01b`; push v2 - `sha256:7f6c0e553cb7daa076e46fb5a9e615e76153017e3f5a96889491ba49237df185`.

### Опыт 1. Liveness

Выбран Pod `web-f998bfc9d-f652q`, UID `da63dd96-c89e-4898-9b35-f3a37d370e9f`. До отказа: `RESTARTS=0`, `/live` - HTTP 200, `/ready` - HTTP 200. Вызов `/you-are-death` вернул HTTP 200, следующий `/live` - HTTP 503. В событии Pod Kubernetes указал `Liveness probe failed` и `Container web failed liveness probe, will be restarted`.

После перезапуска имя и UID Pod остались прежними, `RESTARTS` стал 1, Pod снова стал Ready, `/live` вернул HTTP 200. В логах client до события были ответы HTTP 200. Во время перезапуска в `20:22:17Z` записана одна ошибка `Connection refused`; затем запросы снова завершались HTTP 200. При первом запуске приложения в `20:20:49Z-20:20:57Z` также были ошибки соединения, пока реплики проходили startup/readiness проверки.

Фрагменты логов client (время UTC):

```text
до:      20:21:39Z  HTTP 200  web-f998bfc9d-f652q  version=v1
во время: 20:22:17Z  ERROR Connection refused
после:   20:22:23Z  HTTP 200  web-f998bfc9d-qr5s2  version=v1
```

Ожидал: После отказа `/live` станет 503 и kubelet перезапустит контейнер

Наблюдал: `/live` вернул 503; зафиксировано событие liveness; тот же Pod восстановился с `RESTARTS=1`. Во время восстановления client один раз записал `Connection refused`, затем снова получал HTTP 200.

Объяснение: Liveness проверяет состояние контейнера. Kubernetes перезапускает контейнер внутри Pod, поэтому UID Pod сохраняется. Пока контейнер проходит запуск и пробы, клиент может получить временную ошибку.

### Опыт 2. Readiness

Выбран Pod `web-f998bfc9d-qr5s2`, UID `5f609509-8834-4827-8ab2-c8dc33644ef7`, IP `10.244.0.29`. До переключения `/`, `/live`, `/ready` возвращали HTTP 200; endpoint имел `conditions.ready: true`.

Вызов `/not-ready` вернул HTTP 200, после чего `/ready` отвечал HTTP 503, а `/live` - HTTP 200. Затем Pod стал `READY=false`; в EndpointSlice для него было `conditions.ready: false`. `RESTARTS` остался 0. В течение наблюдения client продолжал получать HTTP 200 от других готовых Pod, ошибок в этом интервале не было. После `/ready-again` Pod снова стал Ready, endpoint получил `conditions.ready: true`; позднее в логах client снова появился ответ `web-f998bfc9d-qr5s2` с HTTP 200.

Фрагменты логов client (время UTC):

```text
до:      20:37:35Z  HTTP 200  web-f998bfc9d-qr5s2  version=v1
во время: 20:37:43Z  HTTP 200  web-f998bfc9d-sqggm  version=v1
после:   20:39:41Z  HTTP 200  web-f998bfc9d-qr5s2  version=v1
```

Ожидал: При `/not-ready` Pod останется жив, но Service исключит его из обычной маршрутизации

Наблюдал: `/ready` - 503, `/live` - 200, Pod Ready=false, endpoint ready=false; `RESTARTS=0`

Объяснение: Readiness управляет допуском Pod к трафику Service и сама по себе контейнер не перезапускает. Port-forward идёт напрямую к выбранному Pod, поэтому через него можно вызвать `/ready-again`, даже когда Pod исключён из endpoints Service.

### Опыт 3. RollingUpdate

Перед обновлением Deployment масштабирован до четырёх реплик; `minReadySeconds: 5`, `maxSurge: 1`, `maxUnavailable: 0`. Старый образ - v1. В манифесте изменён только образ на `localhost:5001/homework2-web:v2`.

Во время обновления наблюдались старая ReplicaSet `web-f998bfc9d` и новая `web-5b975dbb89`. Новая ReplicaSet последовательно увеличивалась до четырёх Pod, старая уменьшалась до нуля. В логах client во время перехода были ответы HTTP 200 как от v1, так и от v2; после завершения оставались ответы v2. В интервале обновления `20:24:45Z-20:25:59Z` в логах client были только ответы HTTP 200; HTTP-ошибок в этом интервале не было.

Две старые реплики (`web-f998bfc9d-sqggm` и `web-f998bfc9d-f652q`) оставались в `Terminating` дольше пяти минут после того, как Deployment начал их удаление. После фиксации этого состояния были удалены только эти два Pod, уже находившиеся в `Terminating`, чтобы завершить rollout. Это отмечаю как особенность данного прогона. Итоговый Deployment успешно завершил rollout, старый ReplicaSet имеет 0 реплик.

Фрагменты логов client (время UTC):

```text
до:       20:56:45Z  HTTP 200  web-f998bfc9d-sqggm  version=v1
во время: 20:56:51Z  HTTP 200  web-5b975dbb89-fjfgk  version=v2
после:    20:57:59Z  HTTP 200  web-5b975dbb89-l4zhw  version=v2
```

Итоговые четыре Pod версии v2, все `Ready`, `RESTARTS=0`:

Pod `web-5b975dbb89-fjfgk`: UID `538b716d-9c3e-4cd2-97e1-c4615e407c68`, ReplicaSet `web-5b975dbb89`, образ `homework2-web:v2`.

Pod `web-5b975dbb89-l4zhw`: UID `edceff66-9f26-4f5c-b7cb-721ebe7507ae`, ReplicaSet `web-5b975dbb89`, образ `homework2-web:v2`.

Pod `web-5b975dbb89-r7ssq`: UID `d3569186-eae4-4e2b-88bd-d111eb029e05`, ReplicaSet `web-5b975dbb89`, образ `homework2-web:v2`.

Pod `web-5b975dbb89-v874h`: UID `0d4fc9f2-e9d3-4fc9-889d-cec615096781`, ReplicaSet `web-5b975dbb89`, образ `homework2-web:v2`.
Ожидал: Новые Pod будут по одному проходить пробы и становиться доступными до удаления старых

Наблюдал: Client видел ответы v1 и v2 во время перехода; rollout завершился с четырьмя готовыми v2 Pod

Объяснение: Readiness и `minReadySeconds` задерживают удаление старых реплик до готовности новых. `maxSurge: 1` ограничивает временное превышение заданного числа реплик, а не общее число создаваемых новых Pod за весь rollout.

### Команды запуска и проверки

Из каталога проекта:

```text
kubectl --context kind-hosting-lab apply -f working/homework-2/k8s/namespace.yaml
kubectl --context kind-hosting-lab apply -f working/homework-2/k8s/configmap-app.yaml
kubectl --context kind-hosting-lab apply -f working/homework-2/k8s/secret-app.yaml
kubectl --context kind-hosting-lab apply -f working/homework-2/k8s/service-app.yaml
kubectl --context kind-hosting-lab apply -f working/homework-2/k8s/deployment-app.yaml
kubectl --context kind-hosting-lab apply -f working/homework-2/k8s/configmap-client.yaml
kubectl --context kind-hosting-lab apply -f working/homework-2/k8s/deployment-client.yaml
kubectl --context kind-hosting-lab -n homework-2 rollout status deployment/web --timeout=180s
kubectl --context kind-hosting-lab -n homework-2 rollout status deployment/client --timeout=180s
kubectl --context kind-hosting-lab -n homework-2 logs -f deployment/client --timestamps
```

### Удаление ресурсов домашней работы

```text
kubectl --context kind-hosting-lab delete namespace homework-2
```

Кластер, namespace `hosting-lab` и общий контроллер Traefik не удаляются.





