
# 14.30.30715         17.0.23
# 14.31.31108         17.1.6
# 14.32.31342         17.2.22
# 14.33.31631         17.3.4
# 14.34.31948         17.4.14
# 14.35.32217.1
# 14.36.32544         17.6.11
# 14.37.32826.1
# 14.38.33133         17.8.3
# 14.39.33321-Pre

$versions = (
    (New-Object PSObject -Property @{ Version="17.10.34916.146"; Url="https://download.visualstudio.microsoft.com/download/pr/4bc0c2da-4e6d-4a88-9eaa-0748022737fb/a96393451a176f8ec4571814c0e467d3b8bc32e2cafaa42df870e28e278fc344/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.34902.99"; Url="https://download.visualstudio.microsoft.com/download/pr/aad5587f-48a4-49c8-842a-b7209eedb40c/332b99cc82a28e8fe75ce0b144cdf97859b07dd0f5cfb6698335779c644fd3d9/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.34902.100"; Url="https://download.visualstudio.microsoft.com/download/pr/84aae541-7bd8-4757-be47-7281591905db/64fa11f4210012df342fbfaab5af4111572de567c84e02a2d63133103fad9e94/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.8.34902.127"; Url="https://download.visualstudio.microsoft.com/download/pr/a8a3940c-d415-4078-8df8-6af787f56dfa/d8efe4cb5f8bfd75a6228938b0cf84ac1c3d98acbf89dfbcb6183536ecfbfe21/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.34728.177"; Url="https://download.visualstudio.microsoft.com/download/pr/eae9c4c2-34c9-4eb5-bdc2-889d69ee93ec/962b39b86468e34699011753107663e375d721a7b09fe42a51fb5c4dc4a17f81/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.8.34728.176"; Url="https://download.visualstudio.microsoft.com/download/pr/ec7bd8ef-2c51-4e4f-a83f-9087ffbe8b76/a07921dc7dadec2e5a112a752419664a8912492aad83a8ae104690b44b9ff6b7/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.34729.48"; Url="https://download.visualstudio.microsoft.com/download/pr/17c40463-62d5-4fd2-bdc7-117da406cea1/272c8a99d7aa6c3f211e481a594c3c746c538515e4304cd589d5cc3d2a064230/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.34629.265"; Url="https://download.visualstudio.microsoft.com/download/pr/0de9357c-f4ae-45d3-80ca-5cd1d8badb0f/4fba9ac8e2f1e31ce334643f5ac0071ef6cc67724cef96cc44e780c46459c492/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.8.34701.33"; Url="https://download.visualstudio.microsoft.com/download/pr/cf977820-7491-4d7f-bd0f-500597f0ea0c/9271cd86da634e354be6035c6aaaffd7c62e458f39410812fcb3f35f4e57d908/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.34701.35"; Url="https://download.visualstudio.microsoft.com/download/pr/a851fc84-7739-4b67-a7da-2c8564e30b38/b4133f16d790c3ee7325fff80c47094d94dff44b426b86db9013b200bb669ce2/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.34601.182"; Url="https://download.visualstudio.microsoft.com/download/pr/0b462b3a-f38b-4cb3-b1e9-d24011aadb76/42e7ac6bc3772145539b0eb56f9ab8c27e066f263c95a2675b7b124fec5cb169/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.34601.181"; Url="https://download.visualstudio.microsoft.com/download/pr/82ad42d8-b267-4be7-9ae0-cbd5690c2fd4/235b25d73744a96f8a5dda7553a42f6e1d196d77690eca5206de81c7b04515e4/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.8.34601.278"; Url="https://download.visualstudio.microsoft.com/download/pr/03aef663-a3da-4cdd-ac33-9ff2935267ba/fc12f5b47ac9ec42064cfad9e40efe3b88ef5468e82bafec7839ef3296fd88a3/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.8.34525.116"; Url="https://download.visualstudio.microsoft.com/download/pr/5bebe58c-9308-4a5b-9696-b6f84e90a32e/a2e920fe6fc18aba57bb4b1a70865be01888aa21dd8c7f6a9ec7b4aa25c8cfaa/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.8.34511.84"; Url="https://download.visualstudio.microsoft.com/download/pr/94f523ce-4fb4-4d35-83ec-e749572654de/62a94be40397078cdb3f4771a252dc0a085bab1f4ed120d10b6b8923de703346/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.34408.132"; Url="https://download.visualstudio.microsoft.com/download/pr/56ded9a0-874c-4660-a5ca-e2dcedfb63db/c2aa420d3320b1df68e4fda5451bee92956fe6db758d8bd87072ff0c3a416baa/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.8.34408.163"; Url="https://download.visualstudio.microsoft.com/download/pr/78eb9d79-decd-4704-adc0-78dba2473667/03d6de5fa66fbdfeee0f0d338d0923008b333ebab9743517d5c668ec51394006/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.5.33530.505"; Url="https://download.visualstudio.microsoft.com/download/pr/50042acc-a12d-4dfe-a272-b109b15b7cd6/27f2a0c982ed9207130b4d1e260940d1eb269b600dd43048493bbb9125678203/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.7.34302.85"; Url="https://download.visualstudio.microsoft.com/download/pr/47b236ad-5505-4752-9d2b-5cf9795528bc/87684889f46dec53d1452f4a0ff9fec1ac202a97ebed866718d7c0269e814b28/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.3.32901.215"; Url="https://download.visualstudio.microsoft.com/download/pr/8106c1cc-df87-4854-8865-3b46bef5867c/771fbda86c3f12a52dc9999e39ad80a7cbbd16b9c0b940671b03d3364fe002d4/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.1.32421.90"; Url="https://download.visualstudio.microsoft.com/download/pr/949751db-6687-4a88-a0cf-047f10908a29/3d9b988f8850d1af4fae60807d8695249731fc19488eed013d1dd4a21c7309d5/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.34408.137"; Url="https://download.visualstudio.microsoft.com/download/pr/a265c447-ec7a-49f4-b780-7ab70f920bbb/4cb83c7dd5bf51f81881ced8b727c451fae817e5c059f778dbc1424c2cc2906f/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.34408.133"; Url="https://download.visualstudio.microsoft.com/download/pr/fc27c72a-f6a7-4785-9135-c7d7adc0078c/f8177acdd5b008def03640e5163cf81f33462c8acdf290c10882ad19eff5d0a0/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.8.34330.188"; Url="https://download.visualstudio.microsoft.com/download/pr/63b5064f-af60-4cbe-96cd-a9dd9d41ee3d/436695f5b9083e37a62f63326dd4c2757b5780316f2c7e6ba0fdcee0770bfe67/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.8.34322.80"; Url="https://download.visualstudio.microsoft.com/download/pr/c5c3dd47-22fe-4326-95b1-f4468515ca9a/48a69924d9e70fe24b0af880dcc69a15a82b7a36fa1c24a4e7e38bdbfb9a4dc0/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.8.34316.72"; Url="https://download.visualstudio.microsoft.com/download/pr/1ddfd51d-41a3-4a5f-bb23-a614eadbe85a/0424cf7a010588b8dd9a467c89c57045a24c0507c5c6b6ffc88cead508b5f972/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.34302.98"; Url="https://download.visualstudio.microsoft.com/download/pr/10d6d1e3-ed79-4103-a8f8-59f373d5a58e/fe74409f9e70700caf1dfb6883fe3c1f0dc3c9049d66ea3cd34b294b6ce1e32d/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.34302.79"; Url="https://download.visualstudio.microsoft.com/download/pr/9f7805e8-b0de-40b7-a392-51e47eb7868b/083d29ede656238d84a6a00f6cb25d2b0313af4f8d4a54cdd478c49ee8299d4f/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.34302.75"; Url="https://download.visualstudio.microsoft.com/download/pr/0cfb09bb-60ee-494a-887d-9697d4e466e4/3903ed05dab568192d3920b8096004fec48ab2e0609e19738f1a654bedaa859a/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.8.34309.116"; Url="https://download.visualstudio.microsoft.com/download/pr/eb105084-8c42-4491-a292-51b4ab48d847/8e07efcfc41db883fa4e8136c9bfb572aadfcc98512c205a7b9e43564ee404ff/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.34221.33"; Url="https://download.visualstudio.microsoft.com/download/pr/09689172-23a4-4469-8caf-24fedb9a1b64/5a9884a1caf0a7e74e8bb492d8929505369958a34d3cf664c9e4b96cbb8e14ed/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.34221.32"; Url="https://download.visualstudio.microsoft.com/download/pr/e4b9a8d4-87df-47f8-b17f-112c373446e4/37aca65abe66f3a6322d93d85e45001380334cd1dbe359fe5d7083f2e509d694/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.34221.16"; Url="https://download.visualstudio.microsoft.com/download/pr/922387c9-941d-4b23-a0f4-039a3fe494e2/dc0d83b1c96f9c193a2e653e31182960793c8eda7f4b2bac2f8c6b90138256ac/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.34202.201"; Url="https://download.visualstudio.microsoft.com/download/pr/9b1df50c-1018-45df-b1ed-917cecea4408/5649e92c5e338f361b199cac4ef901373c8f6c30a0fe9ac9742b2137727dda3d/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.34202.200"; Url="https://download.visualstudio.microsoft.com/download/pr/5af355a5-8f4d-419c-9d3c-4823e6ae3e73/f71980ca8429b0f97bd10fb41f9e15f5029c7bc63952ad2a532d749c86a88373/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.34202.202"; Url="https://download.visualstudio.microsoft.com/download/pr/c5b01ce9-9d49-499b-a2d7-a57d65a12f75/6e40d78bd72b065e959b18858b043425348bec24ce8a43e878473986ae12c133/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.34031.178"; Url="https://download.visualstudio.microsoft.com/download/pr/27b00650-dd0d-4ee7-a7f9-cc469ca32da4/1aab3100e7e7ae01f2688a9369f861d7e475c54ccc9d0558a6723c3ede0160b8/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.34031.109"; Url="https://download.visualstudio.microsoft.com/download/pr/df29487e-be3b-49f9-96ee-03e3258b5b31/76d8b6c1b33b24e74ae52948433d3bb6d9e8b438a6d4f505701f47f75d69e0bb/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.34031.104"; Url="https://download.visualstudio.microsoft.com/download/pr/750bdd5a-9dc3-4f2d-8770-7cf271f96805/8bcd4e5d942d8dc9dced87bf017e1b87f41d6c3096afb22c61d9941b58cd0a17/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.33927.249"; Url="https://download.visualstudio.microsoft.com/download/pr/9f04ac07-6b32-4131-8dcc-985893eca9d9/894751857911647a23488a24a596d4ed30bf28f7d94721ac4dafda827a7d9cca/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.33927.290"; Url="https://download.visualstudio.microsoft.com/download/pr/a7b6e39e-f388-4791-95fe-0d90625f1e5e/644668b9c30016d0ae750a2de6599c45a855d9e231360cd56669be7fab14f4c8/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.33927.135"; Url="https://download.visualstudio.microsoft.com/download/pr/1b408b16-d625-4485-9c86-1164085c59a1/fa3aa4e04ca9ef3dedf3cc1e43d840cd31d3bfbfc9f543c767f13f4545db693b/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.33829.165"; Url="https://download.visualstudio.microsoft.com/download/pr/0e53aa16-2e8c-4ed2-85e4-8ef835450fcc/0c7ae48cf06eff49de7a27afb4b9ef2632235380a4b72e1eb7a85b421986522e/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.33829.357"; Url="https://download.visualstudio.microsoft.com/download/pr/67cb4c13-1e6d-4bf5-97ed-93636beebd7d/cd527d2dd0ef93387a5f8a4c5e1e07902a75c0595c013c0d4bdf6ddb3c94ade0/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.33829.164"; Url="https://download.visualstudio.microsoft.com/download/pr/d6901a6a-a664-48bc-b38b-50b987e54a4e/189bb5af7cde0168255c4ecaacaa4c38ec48a10c6510cf22c29959b56c2df167/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.33829.163"; Url="https://download.visualstudio.microsoft.com/download/pr/60029857-49a0-4e99-94d0-5a0a9b1f98e6/cc95bfc8b8ca80dc5b256989f55cb5a6fdf76d97975af2d121dda770a0a17697/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.33815.320"; Url="https://download.visualstudio.microsoft.com/download/pr/33081bfc-10f1-42d4-8f5a-df6709b8b105/f6f74038e02cd81ac6950aa54ce00f9776e28014109b25faf2a6491208f3a19f/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.33801.468"; Url="https://download.visualstudio.microsoft.com/download/pr/085e1c65-1da0-4521-9bc1-64be775daa71/f87d35ed6ff3e7221aa4b4119b3a65184b280d2d34aa6c4979c5b4e33879426b/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.33801.306"; Url="https://download.visualstudio.microsoft.com/download/pr/9ea2fde2-2c8a-4f47-828c-28fff33f2bc8/1c5acf9d47622eb7bcd8875c971f8418ca7ed5e46386239fdd27a55e72626c6c/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.33801.349"; Url="https://download.visualstudio.microsoft.com/download/pr/9133358e-451c-4921-81dc-7406a86a1942/dbe1ca2f538eed70d110819bc53567eabf81581715c59d755b1ce42041d21a56/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.33801.228"; Url="https://download.visualstudio.microsoft.com/download/pr/1fbaaf4e-3940-45b0-9177-54af8e4a482b/48554b1bb8c79fa87503c29e18149ae644a76929f906e59a7fbc5a70c8006c45/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.33723.286"; Url="https://download.visualstudio.microsoft.com/download/pr/db3d4c0f-3622-4e9b-bc48-7b4d831a33a7/84f9c26182f19bde22b8d8d501e3bbe0ce20d4ad3698edaec5ed83bca0672b1c/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.33717.318"; Url="https://download.visualstudio.microsoft.com/download/pr/7d11b3df-9f2f-4fe7-bec2-ba4ade70c0e8/ff8318c5ca51c0c8ce6fab2f9e81dccf1f9a36746e2fe11eceb51176e55b9a34/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.6.33712.159"; Url="https://download.visualstudio.microsoft.com/download/pr/12bf87fa-ff4f-4b5d-9fb2-2b1c1b59eb10/4ce0031a137a7d30c88ca84361275077678386aa48c7cf4bc2f1b9789c1f8107/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.33603.86"; Url="https://download.visualstudio.microsoft.com/download/pr/0bb9a5f5-5481-4efe-92ab-cca29a90fa5e/adbfb904ddfc115ae7df00098df92d4e545a5eb062ffea8a93f7b8df8d509ff3/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.33530.394"; Url="https://download.visualstudio.microsoft.com/download/pr/44b5bcc5-a671-4e1b-a35d-17b7c556ecf4/fa1a0f8d9a4a1e227f39f648cb2baf97fdc842587f03c644128ef6e447b9b19c/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.33530.339"; Url="https://download.visualstudio.microsoft.com/download/pr/1fd6637b-6d0e-4079-9d03-4fa7610bc313/605da123e04774851e84692b742ca28de527564427d47b5b9f54ba1f0e68b97f/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.33502.350"; Url="https://download.visualstudio.microsoft.com/download/pr/d1ed8638-9e88-461e-92b7-4e29cc6172c3/38b09fc09ae9e590b73ae6752a0ebfd62579798969041bd341689273b842bc10/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.33502.348"; Url="https://download.visualstudio.microsoft.com/download/pr/e0e8bd3a-cf46-4749-81c8-e02f44608423/07a5d546488f233523e41552c0f64c9f106e49807e9d6781227f669a866f58f9/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.33502.349"; Url="https://download.visualstudio.microsoft.com/download/pr/1176ff27-964b-42ad-b034-3173d4a66ee7/1e37ac87d4102034bcdb1655d154202df3b84571d4cb853a598f43ba6bbf5138/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.33403.182"; Url="https://download.visualstudio.microsoft.com/download/pr/23ed7a01-a363-4dd3-8efb-5bf5b2cd89fd/03938dc80912af7094e1f6a256b481c59822e548b3bf809cb2770c620c81d25d/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.33402.178"; Url="https://download.visualstudio.microsoft.com/download/pr/781ac435-b1fc-489a-839a-1950c16bdb9c/559c30c16c3088219ca7dc180fbdac98644f265499a3dd815409c94ccf2549c1/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.33402.176"; Url="https://download.visualstudio.microsoft.com/download/pr/af689358-efba-483d-b2fc-103be548efd1/316a9f70e30607db56a500baf1146c6c846392cbac0ca85994e054c8ceb7cbdb/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.33213.308"; Url="https://download.visualstudio.microsoft.com/download/pr/0502e0d3-64a5-4bb8-b049-6bcbea5ed247/8f62176e804f2310bd46fc90c2bc7f7d9aa26476a4ef2dd1d4f55f6fe1ae480b/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.33214.139"; Url="https://download.visualstudio.microsoft.com/download/pr/8cd2500f-a139-4b34-9306-f71f02f43d7d/b539960258479c17c32214461eb8563c2f28c8bc96b0e82d28dd24570df5910c/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.33214.273"; Url="https://download.visualstudio.microsoft.com/download/pr/9561daa7-f9a0-4912-ba45-2ba75e95b388/57858237c8f27b81aae56547bf8c7a5e4ac977db4c62ecae2b404fb1a92bcec3/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.33205.214"; Url="https://download.visualstudio.microsoft.com/download/pr/8f480125-28b8-4a2c-847c-c2b02a8cdd1b/f769c3d83f7ad96a73c4489c68911066c0a0445efc0b7be5dcf30f0ea8a2f4d0/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.33130.433"; Url="https://download.visualstudio.microsoft.com/download/pr/d19199a0-1717-4464-8f26-42c06ff5902d/9c4b95a014ad52d4a3d521b7230f8a15b41b114d3c6846b32dcc381b0ec9bda5/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.33130.402"; Url="https://download.visualstudio.microsoft.com/download/pr/4fa6f781-e75f-43a7-bf51-066503f685ae/7bc8ecedc79b5174525c9d36477fdc0a1c860f3dbaee06e7d53affcd88e6123a/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.33122.133"; Url="https://download.visualstudio.microsoft.com/download/pr/f3f8db49-2cd0-43df-9ced-12dcb6b3954b/a2912c0564e3d5b206dcb01361ef8676ecdfcf8c0ec857273fa6459d230befc3/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.33110.190"; Url="https://download.visualstudio.microsoft.com/download/pr/2160190b-bb01-4670-9492-34da461fa0c9/9454eaf7dd2893faacf4b564bc7e9d5238b7e3b4f47afe7c7b2c1e2a165b7e17/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.4.33103.184"; Url="https://download.visualstudio.microsoft.com/download/pr/de71f641-13a1-4991-92dc-ba1d44ac1605/3c4efccb9c4849c775c622a0d16474d7edc61267bea6727fa7f7afc95de42376/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.33027.314"; Url="https://download.visualstudio.microsoft.com/download/pr/001cfecc-e0eb-4eb0-8dd6-51533bce72d7/cec23cc5ffa7b3761993dab21b250537d3cf66a8524569c79a6ea182dbacf99c/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.33027.175"; Url="https://download.visualstudio.microsoft.com/download/pr/b98afa45-28f4-457d-999f-0f33b2d17ca9/dd8279aec56cb24fb4544bf2f36c7cf547cb107b27c625efa9c2ef1a74c364ec/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.32929.388"; Url="https://download.visualstudio.microsoft.com/download/pr/d66ab022-583e-4b0b-998b-d60f5173aa4e/569d70493499d754edca8dee5d0c2a16dbfc17b9382e68fbc1e07f29061d8d38/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.32929.387"; Url="https://download.visualstudio.microsoft.com/download/pr/01394260-7b49-458b-b841-16fd4902bbf3/9c84e348fad08e626af65a2de9e483de16862bd1320c952524106aa8065c0a66/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.32901.213"; Url="https://download.visualstudio.microsoft.com/download/pr/cc0385ef-f2fd-4e37-b989-8983ead82e53/32c95eafae7391786aa0618e49a693c26b6187c0ad8acad68a456778cb7adffe/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.32901.226"; Url="https://download.visualstudio.microsoft.com/download/pr/208dee70-576c-4f16-9c40-34b63a4d6633/126e00f3da4a2270994abc0864f9200652e343855f7a82d6a0f7872e04093329/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.32802.462"; Url="https://download.visualstudio.microsoft.com/download/pr/91492062-c2a6-4ff6-81a2-c9646c7ebd02/c50f05c0d952b2cb2ce698ccc6b683caefdc39db945a1e2a3abd12757aba8f8a/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.32802.463"; Url="https://download.visualstudio.microsoft.com/download/pr/dcdff1ed-3b4e-45c2-82e5-5620c33ae0ac/732908c7713b73eedf35276efd9f64c6d18caa8245eb5f2358b13a970c5ddbc9/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.32630.192"; Url="https://download.visualstudio.microsoft.com/download/pr/91cf5cbb-c34a-4766-bff6-aea28265d815/97e3a74aad85ccb86346ebb76baa537e166cbab550d7239487c92a835e10d4f1/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.32630.193"; Url="https://download.visualstudio.microsoft.com/download/pr/aa829f88-5297-46ce-8382-2373da8e892f/b7de5b44b229dcf41b58c5bf9e936a733f0623e513f87af4defc41cae48a7ea5/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.32616.157"; Url="https://download.visualstudio.microsoft.com/download/pr/32bd2bc7-34ab-4d3d-abbf-526f0be7a954/fb48d292c89281cecb7a17bcc5aba8d62aa81eddf5a502692ec64e5eb43b801d/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.32602.215"; Url="https://download.visualstudio.microsoft.com/download/pr/2246570b-d03f-487d-8eeb-41e4a9c93199/586ee66cd76232033290f2806141386865e87730e7776116eef35a7316fb0af1/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.32602.201"; Url="https://download.visualstudio.microsoft.com/download/pr/59002ba3-56cb-437d-bb44-894dbc864638/ef80e1940ac56a3019ad9b01d6ff590e707e4f44ebb7be3bd6797867ed109b4f/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.32526.322"; Url="https://download.visualstudio.microsoft.com/download/pr/ea24168f-493e-42f7-9d95-83e763d3b0a9/f2bfc85d51f3db55aa85e8d7c6d0bdca7d6718b0885391f6b41e62e57475841c/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.32519.379"; Url="https://download.visualstudio.microsoft.com/download/pr/d31b13df-910a-40c8-aca6-778a2a7a56e7/6eda8dfcb55a17ca9aa41279e655079f302cc809433c8e3758e7d53c0969546e/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.32516.85"; Url="https://download.visualstudio.microsoft.com/download/pr/05734053-383e-4b1a-9950-c7db8a55750d/8453f22d1923c8965d4dc8c8704d03b859b1bc9b7b5e698bba3e54cd238edcf9/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.2.32505.173"; Url="https://download.visualstudio.microsoft.com/download/pr/dc2793e9-7b80-4f11-9e33-85833e8921a6/f80fd5547351fde319047725aae6a42d3b9a11276ab638901718a56b2e00a046/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.32428.209"; Url="https://download.visualstudio.microsoft.com/download/pr/53edb6f0-82de-49af-a2a1-fe64ca541a25/966f3119b48b8e5df53916dbe643aa2fc7108f8b82169d71579d5844f2089e6a/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.32417.34"; Url="https://download.visualstudio.microsoft.com/download/pr/beefa99f-472d-4a14-a29e-96f9c9c875d5/0da4bfd9c7caa955673ba666c09cd768bfe3453ae861f0394968728df5749fbd/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.32407.392"; Url="https://download.visualstudio.microsoft.com/download/pr/d0189d86-30d7-49a0-b7dc-9c28bdb4d33a/54fcb9e8dd416d57d84379bffd58c92732ad436193064266875702451c522bba/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.32228.444"; Url="https://download.visualstudio.microsoft.com/download/pr/de440841-5e06-40ef-8ec3-47ef227ccb00/d20df0ae525c09086448732b9cc89bfdef099bd5b73066abbaabd703783cd372/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.32126.317"; Url="https://download.visualstudio.microsoft.com/download/pr/928b2d78-4b74-4601-9c82-334cdbb1b3b4/66b16f06a5567dd98207000c4e04fd6afb28f54e7711641d834e9462decc2358/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.32112.339"; Url="https://download.visualstudio.microsoft.com/download/pr/ce8663b0-08ed-410a-9f5d-4f9469d1b2cb/0279f6067c003f8b81621502fa95a1df377b1fdd7769a8e80ff63df26756d4e2/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.32014.148"; Url="https://download.visualstudio.microsoft.com/download/pr/99fe5fea-e07c-4e6e-87ef-32a88c6ec393/c4ea44aa066ea725a2fe1e0796857530cd2ae8954cf0d546590db20f8e5d771f/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.32002.185"; Url="https://download.visualstudio.microsoft.com/download/pr/ab119488-4f37-455b-a5de-86064bd15c4e/aafa8b3da26e3103984b2ef6a5debb5cb86b407ec9a40eb94281660edb14ba5e/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.31919.166"; Url="https://download.visualstudio.microsoft.com/download/pr/a53da67f-8d8a-448c-b211-d234d17e6398/810b12ab293714c34c29654ef5089f11bdc49d180236b0f1927f599cdb01d5f3/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.31912.275"; Url="https://download.visualstudio.microsoft.com/download/pr/8cea3871-c742-43fb-bf8b-8da0699ab4af/faa4a70c6431c2bc5e915c6ad07425c17fb1a96cd106405677aa08b6d949ba63/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="17.0.31903.59"; Url="https://download.visualstudio.microsoft.com/download/pr/7aa16be3-9952-4bd2-8ecf-eae91faa0a06/321b8a214aa29dcb92fe5d3887832f2aa75a86a672a2cc1372f191dcd26908d6/vs_BuildTools.exe" })
)

# $preview_setup_url = "https://aka.ms/vs/17/pre/vs_BuildTools.exe"
$download_path = "D:/efs/download"
$full_install_root = "D:/efs/full"
$archives = "D:/efs/archives"

function Download {
    Param (
        [string] $version,
        [string] $url
    )

    $versionPath = "$download_path/$version"
    $filepath = "$versionPath/installer.exe"

    if (!(Test-Path -Path $filepath)) {
        New-Item -ItemType Directory $versionPath
        Invoke-WebRequest -Uri $url -OutFile $filepath
    }
}

function Install {
    Param (
        [string] $version
    )

    $installer = "$download_path/$version/installer.exe"

    New-Item -ItemType Directory -Force "$full_install_root/$version"
    Start-Process -Wait -FilePath "$installer" -ArgumentList @("--installPath", "$full_install_root/$version", "--add", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "--add", "Microsoft.VisualStudio.Component.VC.Tools.ARM64", "--add", "Microsoft.VisualStudio.Component.VC.Tools.ARM")
}

function Uninstall {
    Param (
        [string] $version
    )

    $installer = "$download_path/$version/installer.exe"

    Start-Process -Wait -FilePath "$installer" -ArgumentList @("uninstall", "--wait", "--passive", "--installPath", "$full_install_root/$version")

    Remove-Item -Recurse -Force "$full_install_root/$version"
}

function ZipVC {
    Param (
        [string] $version,
        [string] $compilerVersion,
        [string] $productVersion
    )

    New-Item -ItemType Directory -Force "$archives"
    Compress-Archive -DestinationPath "$archives/$compilerVersion-$productVersion.zip" -Path "$full_install_root/$version/VC/Tools/MSVC/$compilerVersion"
}

New-Item -ItemType Directory -Force "$full_install_root"

foreach ($version in $versions)
{
    $installVersion = $version.Version

    Write-Host "Installer version: $installVersion"
    Download -version $installVersion -url $version.Url
    Install -version $installVersion

    $dir = "$full_install_root/$installVersion/VC/Tools/MSVC"
    Get-ChildItem $dir | Foreach-Object {
        $compilerVersion = $_.Name
        Write-Host "Compiler directory version: $compilerVersion"

        $compilerExeProductVersion = (Get-Item "$dir/$compilerVersion/bin/Hostx64/x64/cl.exe").VersionInfo.ProductVersionRaw
        Write-Host "Compiler exe version: $compilerExeProductVersion"

        ZipVC -version $version.Version -compilerVersion $compilerVersion -productVersion $compilerExeProductVersion
    }

    Uninstall -version $version.Version
}
