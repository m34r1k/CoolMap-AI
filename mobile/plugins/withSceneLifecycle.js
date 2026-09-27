// iOS 27 SDK 로 빌드한 앱은 UIScene 생명주기를 쓰지 않으면 실행하자마자 멈춘다
// (UIApplicationEvaluateRuntimeIssueForNoSceneLifecycleAdoption).
// Expo SDK 57 의 ios 템플릿은 아직 AppDelegate 에서 창을 만들므로, SDK 58 템플릿과 같게 고친다.
//   · AppDelegate 는 React Native 팩토리만 만들고 ExpoReactNativeFactoryProvider 를 따른다
//   · 창은 SceneDelegate(= expo 의 ExpoAppSceneDelegate)가 만든다
//   · Info.plist 에 씬 설정을 넣는다
// SDK 58 이상으로 올리면 템플릿이 이미 이렇게 되어 있으므로 이 플러그인을 지운다.

const fs = require("fs");
const path = require("path");
const { IOSConfig, withAppDelegate, withDangerousMod, withInfoPlist, withXcodeProject } = require("expo/config-plugins");

const SCENE_DELEGATE = `internal import Expo

@objc(SceneDelegate)
class SceneDelegate: ExpoAppSceneDelegate {
  // Extension point for config plugins.
}
`;

const WINDOW_START = /\n#if os\(iOS\) \|\| os\(tvOS\)\n\s*window = UIWindow\(frame: UIScreen\.main\.bounds\)[\s\S]*?#endif\n/;

function withSceneAppDelegate(config) {
  return withAppDelegate(config, (config) => {
    let src = config.modResults.contents;
    if (!src.includes("ExpoReactNativeFactoryProvider")) {
      src = src.replace("class AppDelegate: ExpoAppDelegate {", "class AppDelegate: ExpoAppDelegate, ExpoReactNativeFactoryProvider {");
    }
    src = src.replace(WINDOW_START, "\n    // 창은 SceneDelegate 가 만들고 React Native 도 거기서 시작한다\n");
    if (!src.includes("ExpoReactNativeFactoryProvider") || src.includes("UIScreen.main.bounds")) {
      throw new Error("withSceneLifecycle: AppDelegate.swift 모양이 예상과 달라 고치지 못했습니다");
    }
    config.modResults.contents = src;
    return config;
  });
}

function withSceneManifest(config) {
  return withInfoPlist(config, (config) => {
    config.modResults.UIApplicationSceneManifest = {
      UIApplicationSupportsMultipleScenes: false,
      UISceneConfigurations: {
        UIWindowSceneSessionRoleApplication: [
          {
            UISceneConfigurationName: "Default Configuration",
            UISceneDelegateClassName: "$(PRODUCT_MODULE_NAME).SceneDelegate",
          },
        ],
      },
    };
    return config;
  });
}

function withSceneDelegateFile(config) {
  config = withDangerousMod(config, [
    "ios",
    async (config) => {
      const name = IOSConfig.XcodeUtils.getProjectName(config.modRequest.projectRoot);
      fs.writeFileSync(path.join(config.modRequest.platformProjectRoot, name, "SceneDelegate.swift"), SCENE_DELEGATE);
      return config;
    },
  ]);
  return withXcodeProject(config, (config) => {
    const name = IOSConfig.XcodeUtils.getProjectName(config.modRequest.projectRoot);
    const filepath = `${name}/SceneDelegate.swift`;
    if (!config.modResults.hasFile(filepath)) {
      IOSConfig.XcodeUtils.addBuildSourceFileToGroup({ filepath, groupName: name, project: config.modResults });
    }
    return config;
  });
}

module.exports = function withSceneLifecycle(config) {
  return withSceneDelegateFile(withSceneManifest(withSceneAppDelegate(config)));
};
